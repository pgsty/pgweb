from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('search', '0001_initial')]
    operations = [migrations.RunSQL(
        sql="""
ALTER TABLE search_indexedpage DROP CONSTRAINT search_indexedpage_page_id_b2166df0_fk_docs_id;
ALTER TABLE search_indexedpage ADD CONSTRAINT search_indexedpage_page_id_b2166df0_fk_docs_id
    FOREIGN KEY (page_id) REFERENCES docs(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE search_searchentry DROP CONSTRAINT search_searchentry_document_id_ab01c1f3_fk_search_in;
ALTER TABLE search_searchentry ADD CONSTRAINT search_searchentry_document_id_ab01c1f3_fk_search_in
    FOREIGN KEY (document_id) REFERENCES search_indexedpage(page_id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
""",
        reverse_sql="""
ALTER TABLE search_indexedpage DROP CONSTRAINT search_indexedpage_page_id_b2166df0_fk_docs_id;
ALTER TABLE search_indexedpage ADD CONSTRAINT search_indexedpage_page_id_b2166df0_fk_docs_id
    FOREIGN KEY (page_id) REFERENCES docs(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE search_searchentry DROP CONSTRAINT search_searchentry_document_id_ab01c1f3_fk_search_in;
ALTER TABLE search_searchentry ADD CONSTRAINT search_searchentry_document_id_ab01c1f3_fk_search_in
    FOREIGN KEY (document_id) REFERENCES search_indexedpage(page_id) DEFERRABLE INITIALLY DEFERRED;
""",
    )]
