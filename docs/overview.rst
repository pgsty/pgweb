Overview
========

Dynamic content
---------------
The dynamic content of the website is rendered using Django. The
django project is called "pgweb", and consists of a number of
applications under it. These applications are *not* designed to be
independent, and cross-referencing between them is both allowed and
normal. It should therefor not be expected that they will work if
copied outside the pgweb environment.

For more details about the django implementation, see the django.rst file.

Static HTML content
-------------------
For those pages that don't need any database access or other kinds of
logic, simple HTML templates are used.  Any content here is edited as
plain HTML, and the django template engine is used to wrap this
content in the regular website framework.

All pages handled this way are stored in templates/pages/, with each
subdirectory mapping to a sub-url. The code for rendering these pages
is found in pgweb/core/views.py, function fallback().

Non-HTML content
----------------
Non-HTML content is stored in the media/ directory, which is served up
by django when run under the local webserver, but is expected to be
served up directly by the webserver when deployed in production. This
directory has subdirectories for images, css and javascript, as well
as some imported modules.

Note that there is also /adminmedia/, which is directly linked to the
django administrative interface media files, that are shipped with
django and not with pgweb.

Non-web content
---------------
Non-web content, such as PDF files and other static data, is kept out
of the main git repository in the local static/ directory. Deployment
can populate this directory with rsync or another file copy mechanism.
These files are served by the Django application at the /files/ url.

Batch jobs and integrations
---------------------------
There are a number of batch jobs expected to run on the server, in
order to fetch data from other locations. There are also jobs that
need to run on a different server, such as the ftp server, to push
information to the main server. For more details about these, see the
batch.rst file.
