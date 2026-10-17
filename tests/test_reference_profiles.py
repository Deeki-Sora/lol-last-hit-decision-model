import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from workbench.reference_profiles import codex_text_to_reference,public_patch


class ReferenceProfiles(unittest.TestCase):
    def test_codex_reference_parser_is_non_authoritative_and_extracts_stats(self):
        text='''Patch 26.20\nHealth\n650\n+114 / lvl\nArmor\n38\n+4.8 / lvl\nAttack speed\n0.651\n+2.5% / lvl\nP\nDeathbringer Stance\nQ\nThe Darkin Blade\nCooldown\n14 / 12 / 10'''
        result=codex_text_to_reference(text,'https://riotcodex.net/champions/Aatrox')
        self.assertEqual(result['patch'],'26.20');self.assertEqual(result['base_stats']['hp'],650)
        self.assertEqual(result['base_stats']['hpperlevel'],114);self.assertFalse(result['verified'])
        self.assertIn('P',result['ability_reference']);self.assertIn('Q',result['ability_reference'])
        self.assertEqual(public_patch('16.6.1'),'26.6');self.assertTrue(result['patch_match'])

    def test_automatic_fetch_uses_constructed_slug_and_caches_reference(self):
        from workbench.reference_profiles import fetch_riot_codex
        html='Patch 26.6\nHealth\n650\n+114 / lvl\nP\nPassive'
        with tempfile.TemporaryDirectory() as folder,patch('workbench.reference_profiles.fetch_text',return_value=(html,{'url':'https://riotcodex.net/champions/Aatrox','sha256':'x'})) as mocked:
            result=fetch_riot_codex(Path(folder),'16.6.1','Aatrox')
            self.assertEqual(result['base_stats']['hp'],650);self.assertTrue(result['patch_match']);mocked.assert_called_once()
            cached=fetch_riot_codex(Path(folder),'16.6.1','Aatrox')
            self.assertEqual(cached['cache_path'],'references/codex_16.6.1_Aatrox.json');mocked.assert_called_once()


if __name__=='__main__':unittest.main()
