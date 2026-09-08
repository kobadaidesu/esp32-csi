import math
import unittest

from tools.csi_data import amplitude_change, parse_csi_line


class ParseCsiLineTest(unittest.TestCase):
    def test_parses_frame_and_converts_iq_pairs(self):
        frame = parse_csi_line(
            "CSI: RSSI=-48 len=128 first_word_invalid=0 data=[-3,4,5,12]"
        )

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.rssi, -48)
        self.assertEqual(frame.reported_length, 128)
        self.assertEqual(frame.amplitudes(), (5.0, 13.0))
        self.assertEqual(frame.mean_amplitude(), 9.0)

    def test_skips_invalid_first_word(self):
        frame = parse_csi_line(
            "CSI: RSSI=-60 len=64 first_word_invalid=1 "
            "data=[1,2,3,4,6,8,-5,12]"
        )

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.usable_values(), (6, 8, -5, 12))
        self.assertEqual(frame.amplitudes(), (10.0, 13.0))

    def test_ignores_unrelated_and_invalid_lines(self):
        self.assertIsNone(parse_csi_line("I (10) wifi_csi: CSI enabled"))
        self.assertIsNone(
            parse_csi_line(
                "CSI: RSSI=-48 len=128 first_word_invalid=0 data=[1,nope]"
            )
        )
        self.assertIsNone(
            parse_csi_line(
                "CSI: RSSI=-48 len=128 first_word_invalid=0 data=[1,200]"
            )
        )


class AmplitudeChangeTest(unittest.TestCase):
    def test_returns_mean_absolute_change(self):
        self.assertTrue(
            math.isclose(amplitude_change((5.0, 10.0), (8.0, 14.0)), 3.5)
        )

    def test_empty_previous_frame_has_no_change(self):
        self.assertEqual(amplitude_change((), (8.0, 14.0)), 0.0)


if __name__ == "__main__":
    unittest.main()
