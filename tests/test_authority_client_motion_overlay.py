"""Pure shared overlay validation and rendering; no X4 or filesystem writes."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from authority.client_motion_overlay import (
    MD, MODULES, RECOVERY_APPLY_MODULE, RECOVERY_PLAYBACK_MODULE,
    RECOVERY_APPLY_EPOCH, RECOVERY_APPLY_FIXTURE, append_load_ready_hook,
    render_motion_config, select_motion_sources, transform_motion_control,
    validate_motion_settings,
)


def playback_settings():
    return {
        'port': 23456,
        'lease': '1' * 32,
        'attempt': '2' * 32,
        'generation': '3' * 32,
        'nonce': '4' * 32,
        'router_generation': '5' * 32,
        'timeout': 5,
        'index': 1318,
        'saved_playback_fixture': RECOVERY_APPLY_FIXTURE,
    }


class ClientMotionOverlayTests(unittest.TestCase):
    def setUp(self):
        self.status = ('ready', RECOVERY_APPLY_EPOCH, 10082, 'a' * 64)

    def test_validation_returns_detached_selection_and_rejects_wrong_fixture(self):
        settings = playback_settings()
        selection = validate_motion_settings(self.status, settings)
        self.assertEqual(selection.settings, settings)
        self.assertIsNot(selection.settings, settings)
        self.assertEqual(selection.indices, (1318,))

        candidate_settings = playback_settings()
        del candidate_settings['index'], candidate_settings['saved_playback_fixture']
        candidate_settings['indices'] = [1, 2]
        candidate_settings['player_sector'] = {
            'incarnation': '6' * 32,
            'nonce': '7' * 32,
        }
        candidate_selection = validate_motion_settings(self.status, candidate_settings)
        self.assertIsNot(candidate_selection.settings['indices'], candidate_settings['indices'])
        self.assertIsNot(candidate_selection.settings['player_sector'], candidate_settings['player_sector'])
        self.assertEqual(candidate_selection.indices, (1, 2))

        wrong_status = ('ready', 'b' * 32, 10082, 'a' * 64)
        with self.assertRaisesRegex(ValueError, 'saved-playback fixture'):
            validate_motion_settings(wrong_status, settings)

    def test_source_and_config_rendering_preserve_playback_dependencies(self):
        settings = playback_settings()
        selection = validate_motion_settings(self.status, settings)
        modules, md_names = select_motion_sources(selection.settings)
        self.assertEqual(modules[:-3], MODULES[:-1])
        self.assertEqual(modules[-3:], (RECOVERY_APPLY_MODULE, RECOVERY_PLAYBACK_MODULE, MODULES[-1]))
        self.assertEqual(md_names, MD)

        rendered = render_motion_config(self.status, settings)
        self.assertIn('authority_client_motion_index=1318', rendered)
        self.assertIn('authority_client_motion_saved_playback_fixture="recovery_enh_870"', rendered)
        self.assertNotIn('authority_client_motion_saved_apply_fixture=', rendered)

    def test_control_and_load_hooks_keep_playback_stop_gate(self):
        settings = playback_settings()
        settings['player_sector'] = {
            'incarnation': '6' * 32,
            'nonce': '7' * 32,
            'after_bound': True,
        }
        control = (
            'local net,state,engine,next_hello,failed=nil,nil,nil,0,false\n'
            " if not ffi.C.IsPlayerValid() then return end\n"
            "  assert(state:submit('isolated-client',epoch,tonumber(id),op))\n"
            " assert(state:on_update())\nSetScript('onUpdate',function()end)\n"
        )
        updated = transform_motion_control(control, settings)
        self.assertIn("client_motion:state()=='stopped'", updated)
        self.assertIn('after_bound=true', updated)
        self.assertLess(updated.index("client_motion:state()=='stopped'"),
                        updated.index("state:submit('isolated-client'"))
        self.assertIn('client_motion:tick()', updated)

        load = "SetScript('onUpdate',function()end)\n"
        ready_load = append_load_ready_hook(load)
        self.assertIn("function X4LAN_RECOVERED_CLIENT_LOAD_READY() return state=='done' and not failed end", ready_load)


if __name__ == '__main__':
    unittest.main()
