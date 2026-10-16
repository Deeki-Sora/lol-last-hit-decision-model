import unittest
from event_queue import Event, Transition, advance
from pixel_distance import Observation, position, distance, displacement


class EventTests(unittest.TestCase):
    def test_priority_and_shared_endpoint(self):
        events=[Event(1,2,'c','impact'),Event(1,1,'b','commit'),Event(2,0,'d','later')]
        result=advance([],events,lambda s,e:Transition(s+[e.id]),0,1)
        self.assertEqual(result.state,['b','c'])
        self.assertEqual([e.id for e in result.pending],['d'])

    def test_generated_events_and_initial_state_copy(self):
        original=[]
        def transition(s,e):
            s.append(e.kind)
            return Transition(s,(Event(.5,0,'hit','impact'),) if e.kind=='commit' else ())
        result=advance(original,[Event(0,0,'cast','commit')],transition,0,1)
        self.assertEqual(original,[])
        self.assertEqual(result.state,['commit','impact'])

    def test_no_implicit_source_death_cancellation(self):
        result=advance([], [Event(0,0,'dead','source_death'),Event(1,0,'hit','impact')],
                       lambda s,e:Transition(s+[e.kind]),0,1)
        self.assertEqual(result.state,['source_death','impact'])

    def test_invalid_past_event(self):
        with self.assertRaises(ValueError):
            advance({},[Event(-1,0,'bad','impact')],lambda s,e:Transition(s),0,1)

    def test_duplicate_id(self):
        with self.assertRaises(ValueError):
            advance({},[Event(0,0,'x','a'),Event(1,0,'x','b')],lambda s,e:Transition(s),0,1)

    def test_generated_event_cannot_precede_its_cause(self):
        with self.assertRaises(ValueError):
            advance({},[Event(1,1,'b','a')],lambda s,e:Transition(s,(Event(1,0,'a','b'),)),0,2)

    def test_event_limit(self):
        with self.assertRaises(RuntimeError):
            advance({},[Event(0,0,'a','a'),Event(1,0,'b','b')],lambda s,e:Transition(s),0,2,1)


class PixelTests(unittest.TestCase):
    def test_pair_distance_without_origin(self):
        self.assertEqual(distance(Observation(0,{'a':(0,0),'b':(3,4)}),'a','b'),5)

    def test_camera_translation_cancels(self):
        a=Observation(0,{'a':(10,20)},(5,5))
        b=Observation(.3,{'a':(110,220)},(105,205))
        self.assertEqual(position(a,'a'),position(b,'a'))
        self.assertEqual(displacement(a,b,'a')['distance_px'],0)

    def test_true_relative_movement(self):
        a=Observation(0,{'a':(10,20)},(5,5))
        b=Observation(.3,{'a':(113,224)},(105,205))
        self.assertEqual(displacement(a,b,'a')['distance_px'],5)
        self.assertAlmostEqual(displacement(a,b,'a')['dt'],.3)

    def test_missing_observation_not_fabricated(self):
        a=Observation(0,{'a':None,'b':(0,0)})
        self.assertIsNone(distance(a,'a','b'))
        self.assertIsNone(position(a,'b'))

    def test_scale_and_time_validation(self):
        a=Observation(0,{'a':(0,0)},(0,0),'zoom1')
        with self.assertRaises(ValueError):
            displacement(a,Observation(1,{'a':(0,0)},(0,0),'zoom2'),'a')
        with self.assertRaises(ValueError):
            displacement(a,a,'a')


if __name__=='__main__':
    unittest.main()
