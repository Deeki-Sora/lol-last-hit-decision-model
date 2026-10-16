import unittest
from simulator import Wave,particle,utility

class MechanicsTests(unittest.TestCase):
    def test_xp_without_last_hit_and_no_own_denial(self):
        w=Wave(particle(0,True));a=w.units['A'];b=w.units['B'];m=w.units['B_m1'];a.x=m.x;a.y=m.y
        w.damage(w.units['A_m1'],m,1000)
        self.assertEqual(a.cs,0);self.assertAlmostEqual(a.xp_got,61.75);self.assertEqual(b.xp_got,0)
    def test_outside_experience_range(self):
        w=Wave(particle(0,True));w.units['A'].x=-10000
        w.damage(w.units['A_m1'],w.units['B_m1'],1000)
        self.assertEqual(w.units['A'].xp_got,0)
    def test_committed_projectile_survives_source_death(self):
        w=Wave(particle(0,True));s=w.units['A_c1'];t=w.units['B_m1'];hp=t.hp
        w.committed(s,t,21,slayer=True,flight=.5);s.hp=0;w.env.run(until=1)
        self.assertAlmostEqual(t.hp,hp-21-.04*hp)
    def test_current_hp_damage_recomputed(self):
        w=Wave(particle(0,True));s=w.units['A_c1'];t=w.units['B_m1'];hp=t.hp
        w.damage(s,t,21,slayer=True);w.damage(s,t,21,slayer=True)
        self.assertAlmostEqual(t.hp,(hp*.96-21)*.96-21)
    def test_dead_target_does_not_double_pay(self):
        w=Wave(particle(0,True));a=w.units['A'];t=w.units['B_m1'];a.x=t.x;a.y=t.y
        w.damage(a,t,1000);w.damage(a,t,1000)
        self.assertEqual(a.cs,1);self.assertEqual(a.gold_got,21);self.assertEqual(len(w.deaths),1)
    def test_windup_cancelled_when_killed(self):
        w=Wave(particle(0,True),record=True);s=w.units['A_m1'];t=w.units['B_m1'];s.x=t.x;s.y=t.y
        w.env.process(w.minion_loop(s,0));w.delay(.1,setattr,s,'hp',0);w.env.run(until=.5)
        self.assertFalse(any(e['kind']=='commit' for e in w.events))
    def test_w_cost_once_and_serial_recharge(self):
        w=Wave(particle(0,True));a=w.units['A'];t=w.units['B_m1']
        self.assertTrue(w.w(a,t));self.assertFalse(w.w(a,t));w.env.run(until=2)
        self.assertTrue(w.w(a,t));self.assertEqual(a.mana_spent,80);self.assertEqual(a.charges,0)
        w.env.run(until=10.1);self.assertEqual(a.charges,1)
        w.env.run(until=19.9);self.assertEqual(a.charges,1)
        w.env.run(until=20.1);self.assertEqual(a.charges,2)
    def test_resource_conservation_whole_wave(self):
        for seed in range(4):
            w=Wave(particle(seed),(3,2));r=w.run()
            for k,side in [('A','B'),('B','A')]:
                deaths=[d for d in w.deaths if d['id'].startswith(side+'_')]
                xp_dead=sum(w.units[d['id']].xp*.95 for d in deaths)
                self.assertAlmostEqual(xp_dead+r[k+'_pending_xp'],276.45)
                self.assertLessEqual(r[k+'_xp'],xp_dead+1e-7)
                self.assertLessEqual(r[k+'_cs'],6)
                self.assertAlmostEqual(r[k+'_hp_gross']-r[k+'_hp_healed'],r[k+'_hp_loss'])

if __name__=='__main__':unittest.main(verbosity=2)
