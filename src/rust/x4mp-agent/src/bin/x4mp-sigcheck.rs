//! Offline check of a Linux X4 executable against the agent's pinned build and sites.
//! Usage: x4mp-sigcheck /path/to/X4

use std::process::ExitCode;

use x4mp_agent::elf::{FileImage, Load};
use x4mp_agent::pinned::{self, Image};
use x4mp_agent::sha256::{hex, Sha256};

/// Check the 4096-byte mappings used by the fixed30 agent against PT_LOAD
/// memory ranges, including BSS and the partial pages occupied by a segment.
fn report_constant_pages(loads: &[Load], pages: &[u64], mut report: impl FnMut(bool, String)) -> usize {
    const PAGE_SIZE: u64 = 4096;
    let mut failures = 0;
    for &page in pages {
        let Some(page_end) = page.checked_add(PAGE_SIZE).filter(|_| page % PAGE_SIZE == 0) else {
            report(false, format!("FAIL scheduler const page 0x{page:x} has an invalid range"));
            failures += 1;
            continue;
        };
        let mut overlap = false;
        let mut invalid = false;
        for load in loads {
            if load.memsz == 0 {
                continue;
            }
            let Some(segment_end) = load.vaddr.checked_add(load.memsz)
                .and_then(|end| end.checked_add(PAGE_SIZE - 1))
                .map(|end| end & !(PAGE_SIZE - 1)) else {
                invalid = true;
                break;
            };
            let segment_start = load.vaddr & !(PAGE_SIZE - 1);
            overlap |= page < segment_end && segment_start < page_end;
        }
        if invalid {
            report(false, "FAIL scheduler image has an invalid segment range".to_string());
            failures += 1;
        } else if overlap {
            report(false, format!("FAIL scheduler const page 0x{page:x} overlaps the image"));
            failures += 1;
        }
    }
    if failures == 0 {
        report(true, "PASS scheduler const page candidates outside the image".to_string());
    }
    failures
}

fn main() -> ExitCode {
    let Some(path) = std::env::args_os().nth(1) else {
        eprintln!("usage: x4mp-sigcheck /path/to/X4");
        return ExitCode::from(2);
    };
    let data = match std::fs::read(&path) {
        Ok(data) => data,
        Err(e) => {
            eprintln!("FAIL cannot read {}: {e}", path.to_string_lossy());
            return ExitCode::FAILURE;
        }
    };
    let mut failures = 0;
    if data.len() as u64 != pinned::FILE_SIZE {
        eprintln!("FAIL file size {} (pinned {})", data.len(), pinned::FILE_SIZE);
        failures += 1;
    }
    let mut hasher = Sha256::new();
    hasher.update(&data);
    let digest = hex(&hasher.finish());
    if digest != pinned::FILE_SHA256 {
        eprintln!("FAIL file sha256 {digest}");
        failures += 1;
    }
    let Some(image) = FileImage::new(data) else {
        eprintln!("FAIL not an x86-64 ELF64 executable");
        return ExitCode::FAILURE;
    };
    if image.elf_type() != Some(2) {
        eprintln!("FAIL not ET_EXEC");
        failures += 1;
    }
    match pinned::verify_sites(&image) {
        Ok(count) => println!("PASS build-id and {count} signature sites"),
        Err(reason) => {
            eprintln!("FAIL {reason}");
            failures += 1;
        }
    }
    // Scheduler preconditions in the file (the live agent re-checks them before patching).
    let checks: [(&str, u64, Vec<u8>); 6] = [
        ("decision_cmp_original", pinned::DECISION_CMP_VA, pinned::DECISION_CMP_ORIGINAL.to_vec()),
        ("dt_load_original", pinned::DT_LOAD_VA, pinned::DT_LOAD_ORIGINAL.to_vec()),
        ("dt_min_original", pinned::DT_MIN_VA, pinned::DT_MIN_ORIGINAL.to_vec()),
        ("one_sixtieth_constant", pinned::ONE_SIXTIETH_CONST, (1.0f64 / 60.0).to_le_bytes().to_vec()),
        ("one_twentieth_constant", pinned::ONE_TWENTIETH_CONST, (1.0f64 / 20.0).to_le_bytes().to_vec()),
        ("main_frame_in_flight_initial", pinned::MAIN_FRAME_IN_FLIGHT, vec![1]),
    ];
    for (name, va, want) in checks {
        if image.read(va, want.len()).as_deref() == Some(&want[..]) {
            println!("PASS scheduler {name} at 0x{va:x}");
        } else {
            eprintln!("FAIL scheduler {name} at 0x{va:x}");
            failures += 1;
        }
    }
    // fixed30's constant page must lie outside every PT_LOAD segment of the image.
    failures += report_constant_pages(&image.loads, &pinned::CONST_PAGE_CANDIDATES, |passed, message| {
        if passed { println!("{message}"); } else { eprintln!("{message}"); }
    });
    if failures == 0 {
        println!("PASS executable {} build {}; no files modified", pinned::GAME_VERSION, pinned::STEAM_BUILD);
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reports_pass_only_when_every_page_is_outside_the_image() {
        let load = Load { vaddr: 0x3000, offset: 0, filesz: 0x1000, memsz: 0x1000 };
        let mut messages = Vec::new();
        let failures = report_constant_pages(&[load], &[0x1000, 0x4000], |passed, message| {
            messages.push((passed, message));
        });
        assert_eq!(failures, 0);
        assert_eq!(messages.len(), 1);
        assert!(messages[0].0 && messages[0].1.starts_with("PASS"));

        messages.clear();
        let failures = report_constant_pages(&[load], &[0x1000, 0x3000], |passed, message| {
            messages.push((passed, message));
        });
        assert_eq!(failures, 1);
        assert_eq!(messages.len(), 1);
        assert!(!messages[0].0 && messages[0].1.contains("overlaps"));
    }

    #[test]
    fn invalid_segment_or_page_ranges_do_not_report_pass() {
        let invalid_load = Load { vaddr: u64::MAX, offset: 0, filesz: 2, memsz: 2 };
        for (loads, pages) in [(vec![invalid_load], vec![0x1000]), (vec![], vec![u64::MAX]),
                               (vec![], vec![0x1001])] {
            let mut messages = Vec::new();
            assert_eq!(report_constant_pages(&loads, &pages, |passed, message| {
                messages.push((passed, message));
            }), 1);
            assert_eq!(messages.len(), 1);
            assert!(!messages[0].0 && messages[0].1.contains("invalid"));
        }
    }

    #[test]
    fn rejects_bss_and_partial_page_overlaps() {
        let bss_load = Load { vaddr: 0x3000, offset: 0, filesz: 0x1000, memsz: 0x3000 };
        let partial_load = Load { vaddr: 0x3001, offset: 0, filesz: 1, memsz: 1 };
        for (load, candidate) in [(bss_load, 0x4000), (partial_load, 0x3000)] {
            let mut messages = Vec::new();
            assert_eq!(report_constant_pages(&[load], &[candidate], |passed, message| {
                messages.push((passed, message));
            }), 1);
            assert_eq!(messages.len(), 1);
            assert!(!messages[0].0 && messages[0].1.contains("overlaps"));
        }
    }
}
