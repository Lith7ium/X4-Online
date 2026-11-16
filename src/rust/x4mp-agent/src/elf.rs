//! Minimal ELF64 little-endian reader: maps virtual addresses to file offsets through
//! `PT_LOAD` program headers so signature sites can be checked against a file on disk.

use crate::pinned::Image;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Load {
    pub vaddr: u64,
    pub offset: u64,
    pub filesz: u64,
    pub memsz: u64,
}

pub struct FileImage {
    pub data: Vec<u8>,
    pub loads: Vec<Load>,
}

fn u16_at(data: &[u8], at: usize) -> Option<u16> {
    Some(u16::from_le_bytes(data.get(at..at.checked_add(2)?)?.try_into().ok()?))
}
fn u32_at(data: &[u8], at: usize) -> Option<u32> {
    Some(u32::from_le_bytes(data.get(at..at.checked_add(4)?)?.try_into().ok()?))
}
fn u64_at(data: &[u8], at: usize) -> Option<u64> {
    Some(u64::from_le_bytes(data.get(at..at.checked_add(8)?)?.try_into().ok()?))
}

/// `PT_LOAD` segments of an x86-64 ELF64 executable; `None` for anything else.
pub fn loads(data: &[u8]) -> Option<Vec<Load>> {
    if data.get(..6)? != b"\x7fELF\x02\x01" || u16_at(data, 18)? != 62 {
        return None;
    }
    let phoff = usize::try_from(u64_at(data, 32)?).ok()?;
    let phentsize = usize::from(u16_at(data, 54)?);
    let phnum = usize::from(u16_at(data, 56)?);
    if phentsize < 56 || phnum > 64 {
        return None;
    }
    let mut out = Vec::new();
    for index in 0..phnum {
        let at = phoff.checked_add(index.checked_mul(phentsize)?)?;
        if u32_at(data, at)? == 1 {
            let offset = u64_at(data, at.checked_add(8)?)?;
            let vaddr = u64_at(data, at.checked_add(16)?)?;
            let filesz = u64_at(data, at.checked_add(32)?)?;
            let memsz = u64_at(data, at.checked_add(40)?)?;
            let file_end = offset.checked_add(filesz)?;
            vaddr.checked_add(memsz)?;
            if filesz > memsz || file_end > u64::try_from(data.len()).ok()? {
                return None;
            }
            out.push(Load { offset, vaddr, filesz, memsz });
        }
    }
    Some(out)
}

impl FileImage {
    pub fn new(data: Vec<u8>) -> Option<Self> {
        let loads = loads(&data)?;
        Some(FileImage { data, loads })
    }

    pub fn elf_type(&self) -> Option<u16> {
        u16_at(&self.data, 16)
    }
}

impl Image for FileImage {
    fn read(&self, va: u64, len: usize) -> Option<Vec<u8>> {
        let end = va.checked_add(len as u64)?;
        let load = self.loads.iter().find(|l| l.vaddr <= va && end <= l.vaddr.checked_add(l.filesz).unwrap_or(0))?;
        let start = usize::try_from(load.offset.checked_add(va - load.vaddr)?).ok()?;
        self.data.get(start..start.checked_add(len)?).map(<[u8]>::to_vec)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn synthetic() -> Vec<u8> {
        // ELF64 header + one PT_LOAD mapping file offset 0x100 to va 0x400100 (0x10 bytes).
        let mut d = vec![0u8; 0x110];
        d[..4].copy_from_slice(b"\x7fELF");
        d[4] = 2;
        d[5] = 1;
        d[16..18].copy_from_slice(&2u16.to_le_bytes());
        d[18..20].copy_from_slice(&62u16.to_le_bytes());
        d[32..40].copy_from_slice(&64u64.to_le_bytes());
        d[54..56].copy_from_slice(&56u16.to_le_bytes());
        d[56..58].copy_from_slice(&1u16.to_le_bytes());
        d[64..68].copy_from_slice(&1u32.to_le_bytes());
        d[72..80].copy_from_slice(&0x100u64.to_le_bytes());
        d[80..88].copy_from_slice(&0x400100u64.to_le_bytes());
        d[96..104].copy_from_slice(&0x10u64.to_le_bytes());
        d[104..112].copy_from_slice(&0x10u64.to_le_bytes());
        for (i, b) in d[0x100..].iter_mut().enumerate() {
            *b = i as u8;
        }
        d
    }

    #[test]
    fn maps_virtual_addresses_through_pt_load() {
        let image = FileImage::new(synthetic()).unwrap();
        assert_eq!(image.elf_type(), Some(2));
        assert_eq!(image.read(0x400104, 3), Some(vec![4, 5, 6]));
        assert_eq!(image.read(0x40010e, 4), None, "crosses segment end");
        assert_eq!(image.read(0x400000, 1), None, "outside any segment");
    }

    #[test]
    fn rejects_non_x86_64_elf() {
        let mut d = synthetic();
        d[18] = 3;
        assert!(FileImage::new(d).is_none());
        assert!(FileImage::new(b"#!/bin/sh\n".to_vec()).is_none());
    }

    #[test]
    fn rejects_every_truncated_header_without_panicking() {
        let image = synthetic();
        // The ELF header, program header and file-backed bytes must all be
        // complete, even when the first four bytes are a valid ELF magic.
        for len in 0..image.len() {
            assert!(FileImage::new(image[..len].to_vec()).is_none(), "truncation at {len}");
        }
    }

    #[test]
    fn rejects_overflowing_offsets_and_segment_ranges() {
        let mut image = synthetic();
        image[32..40].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(FileImage::new(image).is_none());

        for field in [72, 80] {
            let mut image = synthetic();
            image[field..field + 8].copy_from_slice(&u64::MAX.to_le_bytes());
            assert!(FileImage::new(image).is_none());
        }
        // FileImage fields are public; a manually constructed bad mapping must
        // also fail closed instead of wrapping its file offset in read().
        let image = FileImage {
            data: vec![0; 8],
            loads: vec![Load { vaddr: 1, offset: u64::MAX, filesz: 4, memsz: 4 }],
        };
        assert_eq!(image.read(2, 1), None);
        assert_eq!(u16_at(&[], usize::MAX), None);
        assert_eq!(u32_at(&[], usize::MAX), None);
        assert_eq!(u64_at(&[], usize::MAX), None);
    }

    #[test]
    fn validates_separate_file_and_memory_segment_sizes() {
        let mut image = synthetic();
        image[104..112].copy_from_slice(&0x30u64.to_le_bytes());
        let image = FileImage::new(image).unwrap();
        assert_eq!(image.loads[0].memsz, 0x30);
        assert_eq!(image.read(0x40010f, 1), Some(vec![15]));
        assert_eq!(image.read(0x400110, 1), None, "BSS is not present in file bytes");

        let mut too_small = synthetic();
        too_small[104..112].copy_from_slice(&0x0fu64.to_le_bytes());
        assert!(FileImage::new(too_small).is_none());

        let mut truncated_file = synthetic();
        truncated_file[72..80].copy_from_slice(&0x108u64.to_le_bytes());
        assert!(FileImage::new(truncated_file).is_none());

        let mut overflow_memory = synthetic();
        overflow_memory[104..112].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(FileImage::new(overflow_memory).is_none());
    }
}
