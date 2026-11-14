import unittest

from tools.docs.docload_encoding import document_encoding, has_utf8_xml_declaration


class DocloadEncodingTests(unittest.TestCase):
    def test_postgresql_10_and_newer_use_utf8_without_xml_declaration(self):
        rawcontents = '<div>发布说明</div>'.encode('utf-8')

        self.assertEqual(document_encoding('15'), 'utf-8')
        self.assertFalse(has_utf8_xml_declaration(rawcontents))
        self.assertEqual(rawcontents.decode(document_encoding('15')), '<div>发布说明</div>')

    def test_development_tree_uses_utf8(self):
        self.assertEqual(document_encoding('0'), 'utf-8')

    def test_pre_10_manuals_keep_latin1_compatibility(self):
        rawcontents = b'<div>caf\xe9</div>'

        self.assertEqual(document_encoding('9.6'), 'latin1')
        self.assertEqual(rawcontents.decode(document_encoding('9.6')), '<div>café</div>')

    def test_xml_declaration_is_detected_independently(self):
        rawcontents = '<?xml version="1.0" encoding="UTF-8"?>\n<div>发布说明</div>'.encode('utf-8')

        self.assertTrue(has_utf8_xml_declaration(rawcontents))
        self.assertEqual(document_encoding('15'), 'utf-8')


if __name__ == '__main__':
    unittest.main()
