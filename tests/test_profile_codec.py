import unittest
from profile_codec import Ndf,Profile,repair
from fixtures import profile

def alliances(data):
    ndf=Ndf(next(raw for name,_,raw in Profile(data).records if name=='Profile'))
    cfg=ndf.object_of_class('TLobbyIAConfig')[0]
    counts={0:0,1:0}
    values=ndf.prop(cfg,'IAConfigs')
    for index,(key,ref) in enumerate(values.data):
        assert key.data==index
        counts[ndf.prop(ndf.objects[ref.data[1][0]],'IAAlliance').data]+=1
    return counts

class ProfileRepairTests(unittest.TestCase):
    def test_nineteen_ai_to_seven(self):
        fixed,report=repair(profile())
        self.assertEqual(report['saved_ai_count'],19)
        self.assertEqual(report['retained_ai_configs'],7)
        self.assertEqual(alliances(fixed),{0:3,1:4})
        self.assertEqual(repair(fixed)[1]['saved_ai_count'],7)

    def test_pact_human(self):
        fixed,_=repair(profile(nato=10,pact=9,player=1))
        self.assertEqual(alliances(fixed),{0:4,1:3})

    def test_vanilla_is_byte_identical_even_with_stale_alliances(self):
        for nato,pact in [(3,4),(4,3),(0,0),(1,1)]:
            with self.subTest(nato=nato,pact=pact):
                data=profile(nato=nato,pact=pact)
                self.assertEqual(repair(data)[0],data)

    def test_second_repair_is_byte_identical(self):
        fixed,_=repair(profile())
        self.assertEqual(repair(fixed)[0],fixed)

    def test_unrelated_records_and_all_existing_objects_survive(self):
        before=Profile(profile());after=Profile(repair(before.data)[0])
        self.assertEqual(before.records[2],after.records[2])
        old=Ndf(before.records[0][2]);new=Ndf(after.records[0][2])
        self.assertEqual(len(old.objects),len(new.objects))
        for a,b in zip(old.objects[1:],new.objects[1:]):
            self.assertEqual(old.raw[a['start']:a['end']],new.raw[b['start']:b['end']])

    def test_count_only_damage(self):
        fixed,report=repair(profile(nato=3,pact=4,saved_count=19))
        self.assertEqual(report['changed_records'],['Profile_Additional_4'])
        self.assertEqual(repair(fixed)[1]['saved_ai_count'],7)

    def test_short_one_sided_expansion(self):
        fixed,_=repair(profile(nato=8,pact=0))
        self.assertEqual(alliances(fixed),{0:3,1:0})
        self.assertEqual(repair(fixed)[1]['saved_ai_count'],3)

    def test_bad_checksum_fails_closed(self):
        damaged=bytearray(profile());damaged[-1]^=1
        with self.assertRaisesRegex(ValueError,'checksum'):repair(bytes(damaged))

    def test_unknown_alliance_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'alliance'):repair(profile(player=2))

if __name__=='__main__':unittest.main()
