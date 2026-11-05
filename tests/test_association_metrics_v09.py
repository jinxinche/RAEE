import unittest
from raee_lite.association_metrics import wilson, evaluate


def pair(requirement='Login works',target='login test',kind='unit',relevant=True):
    return {'requirement':requirement,'observed_target':target,'observed_kind':kind,'expected_kinds':['unit'],'relevant':relevant}

class AssociationMetricsTests(unittest.TestCase):
    def test_exact_negative_and_positive_rates(self):
        rows=[pair(relevant=True),pair(relevant=False),pair(target='payments unrelated',relevant=False),pair(target='payments unrelated',relevant=True)]
        m=evaluate(rows)
        self.assertEqual([m[k] for k in ('TP','FP','TN','FN')],[1,1,1,1])
        self.assertEqual(m['precision'],.5)
        self.assertEqual(m['recall'],.5)
        self.assertEqual(m['false_positive_rate'],.5)
    def test_no_negative_opportunities_no_fpr(self):
        m=evaluate([pair(relevant=True)])
        self.assertIsNone(m['false_positive_rate'])
    def test_wilson_sensible(self):
        self.assertEqual(wilson(2,0),None)
        lo,hi=wilson(10,10)
        self.assertLess(lo,hi)
        self.assertLessEqual(hi,1)
    def test_real_requires_consent(self):
        with self.assertRaises(ValueError):evaluate([pair()],provenance='consented-real')
        self.assertEqual(evaluate([pair()],provenance='consented-real',consent=True)['n_pairs'],1)
    def test_label_is_boolean(self):
        x=pair();x['relevant']='yes'
        with self.assertRaises(ValueError):evaluate([x])

if __name__=='__main__':unittest.main()
