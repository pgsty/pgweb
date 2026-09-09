from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('search', '0002_source_cascade')]
    operations = [migrations.RunSQL(
        sql="""
CREATE FUNCTION docsearch_invalidate_page() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM search_indexedpage WHERE page_id = NEW.id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER docsearch_source_changed AFTER UPDATE OF title, content, file, version ON docs
    FOR EACH ROW WHEN (OLD.title IS DISTINCT FROM NEW.title OR OLD.content IS DISTINCT FROM NEW.content
                      OR OLD.file IS DISTINCT FROM NEW.file OR OLD.version IS DISTINCT FROM NEW.version)
    EXECUTE FUNCTION docsearch_invalidate_page();
""",
        reverse_sql="""
DROP TRIGGER docsearch_source_changed ON docs;
DROP FUNCTION docsearch_invalidate_page();
""",
    )]
