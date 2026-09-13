import datetime as dt
import unittest
from icalendar import Todo
from sync_nextcloud import read_todo, to_tw, to_dav, NextcloudSide

class AdapterTests(unittest.TestCase):
    def test_no_priority_and_date_roundtrip(self):
        c=Todo();c.add('uid','test');c.add('summary','Task');c.add('due',dt.date(2026,10,1))
        mapped=to_dav(to_tw(read_todo(c)))
        self.assertEqual(mapped['priority'],0)
        self.assertTrue(mapped['dateonly'])
        self.assertEqual(mapped['due'].date(),dt.date(2026,10,1))

    def test_write_preserves_alarm_and_vendor_data(self):
        c=Todo();c.add('uid','test');c.add('summary','Old');c.add('x-apple-test','keep')
        from icalendar import Alarm
        alarm=Alarm();alarm.add('action','DISPLAY');alarm.add('description','Reminder')
        alarm.add('trigger',dt.timedelta(minutes=-10));c.add_component(alarm)
        class Resource:
            icalendar_component=c
            def save(self): pass
        side=object.__new__(NextcloudSide);side._raw={'test':Resource()}
        side.update_item('test',summary='New',description='',status='completed',priority=0,
                         categories=[],completed=dt.datetime(2026,9,13,tzinfo=dt.timezone.utc))
        parsed=Todo.from_ical(c.to_ical())
        self.assertEqual(parsed['PRIORITY'],0)
        self.assertEqual(parsed['STATUS'],'COMPLETED')
        self.assertEqual(parsed['PERCENT-COMPLETE'],100)
        self.assertEqual(parsed['X-APPLE-TEST'],'keep')
        self.assertEqual(len(parsed.subcomponents),1)
        self.assertIn('COMPLETED',parsed)

if __name__=='__main__':unittest.main()
