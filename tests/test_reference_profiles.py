import unittest
from workbench.reference_profiles import codex_text_to_reference


class ReferenceProfiles(unittest.TestCase):
    def test_codex_reference_parser_is_non_authoritative_and_extracts_stats(self):
        text='''Patch 26.20\nHealth\n650\n+114 / lvl\nArmor\n38\n+4.8 / lvl\nAttack speed\n0.651\n+2.5% / lvl\nP\nDeathbringer Stance\nQ\nThe Darkin Blade\nCooldown\n14 / 12 / 10'''
        result=codex_text_to_reference(text,'https://riotcodex.net/champions/Aatrox')
        self.assertEqual(result['patch'],'26.20');self.assertEqual(result['base_stats']['hp'],650)
        self.assertEqual(result['base_stats']['hpperlevel'],114);self.assertFalse(result['verified'])
        self.assertIn('P',result['ability_reference']);self.assertIn('Q',result['ability_reference'])


if __name__=='__main__':unittest.main()
