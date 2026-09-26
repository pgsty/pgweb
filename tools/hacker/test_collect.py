import json
import unittest

from tools.hacker.collect import flight_sections


class FlightParserTests(unittest.TestCase):
    def test_utf8_text_record_without_line_separator(self):
        biography = "PostgreSQL 开发者\n\nKeeps every source paragraph."
        wire = '1:I[1510,[],"ProfileHero"]\n'
        wire += f"2:T{len(biography.encode('utf-8')):x}," + biography
        wire += '3:["$","$L1",null,{"type":"contributor","profile":{"name":"Example","bio":"$2","created_at":"$D2026-09-26T00:00:00Z"}}]\n'
        # The wire stream itself is split between separate scripts by Next.js.
        html = "".join("<script>self.__next_f.push(" + json.dumps([1, part]) + ")</script>" for part in (wire[:45], wire[45:]))
        _, sections, _ = flight_sections(html)
        self.assertEqual(sections["ProfileHero"]["profile"]["bio"], biography)
        self.assertEqual(sections["ProfileHero"]["profile"]["created_at"], "2026-09-26T00:00:00Z")

    def test_unknown_content_section_is_preserved(self):
        wire = '1:I[1510,[],"ProfileHero"]\n2:I[9999,[],"FutureSection"]\n'
        wire += '3:[["$","$L1",null,{"profile":{"name":"Example"}}],["$","$L2",null,{"initialItems":[{"title":"Preserve me"}],"total":1}]]\n'
        html = "<script>self.__next_f.push(" + json.dumps([1, wire]) + ")</script>"
        _, sections, _ = flight_sections(html)
        self.assertEqual(sections["FutureSection"]["initialItems"][0]["title"], "Preserve me")


if __name__ == "__main__":
    unittest.main()
