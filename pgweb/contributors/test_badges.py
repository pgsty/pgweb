import io
from datetime import date, datetime, timedelta
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from pgweb.core.models import Organisation, OrganisationType, UserSubmission
from pgweb.util.fields import ImageBinaryField
from pgweb.util.forms import ImageBinaryFormField
from pgweb.util.image import EXIF_ORIENTATION_TAG
from .forms import BadgeForm
from .models import Badge, Badgeholder, Contributor


def image_bytes(size=(400, 200), fmt='PNG', orientation=None):
    output = io.BytesIO()
    image = Image.new('RGB', size, '#336791')
    kwargs = {}
    if orientation:
        exif = image.getexif()
        exif[EXIF_ORIENTATION_TAG] = orientation
        kwargs['exif'] = exif
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


class BadgeImageTests(SimpleTestCase):
    def setUp(self):
        self.field = ImageBinaryField(max_length=1000000, resolution=(150, 150), auto_scale=True, blank=True)

    def test_rotated_and_extreme_aspect_images_become_square(self):
        for size, orientation in (((400, 400), 6), ((400, 200), 8), ((1, 2000), None)):
            with self.subTest(size=size, orientation=orientation):
                data = self.field.to_python(image_bytes(size, 'JPEG', orientation))
                image = Image.open(io.BytesIO(data))
                self.assertEqual(image.size, (150, 150))
                self.assertIn(image.getexif().get(EXIF_ORIENTATION_TAG, 1), (None, 1))

    def test_invalid_unsupported_and_oversized_uploads_rejected(self):
        for data in (b'not an image', image_bytes(fmt='GIF'), b'x' * 1000001):
            with self.subTest(size=len(data)):
                with self.assertRaises(ValidationError):
                    self.field.to_python(data)
        self.assertIsNone(self.field.to_python(None))
        self.assertEqual(self.field.to_python(b''), b'')

    def test_uploaded_file_can_be_read_again_during_form_validation(self):
        raw = image_bytes()
        upload = SimpleUploadedFile('badge.png', raw, content_type='image/png')
        field = ImageBinaryFormField(required=False)
        self.assertEqual(field.to_python(upload), raw)
        self.assertEqual(field.to_python(upload), raw)


@override_settings(ALLOWED_HOSTS=['testserver'], SITE_ROOT='https://pgsql.cc')
class BadgeTests(TestCase):
    def setUp(self):
        for target in ('pgweb.util.signals.send_simple_mail', 'pgweb.util.helpers.send_simple_mail',
                       'pgweb.contributors.forms.send_simple_mail', 'pgweb.account.views.send_template_mail',
                       'pgweb.util.signals.varnish_purge', 'pgweb.util.signals.varnish_purge_xkey'):
            mock = patch(target)
            mock.start()
            self.addCleanup(mock.stop)
        self.manager = User.objects.create_user('manager', 'manager@example.test', 'test-password')
        self.holder = User.objects.create_user('holder', 'private@example.test', 'test-password',
                                               first_name='小明', last_name='张')
        self.other = User.objects.create_user('other', 'other@example.test', 'test-password')
        orgtype = OrganisationType.objects.create(typename='用户组')
        self.org = Organisation.objects.create(name='测试用户组', orgtype=orgtype, url='https://example.test', approved=True)
        self.org.managers.add(self.manager)
        self.badge = Badge.objects.create(org=self.org, badge='中文翻译贡献者', approved=True)
        self.award = Badgeholder.objects.create(badge=self.badge, user=self.holder, awarded_by=self.manager)

    def badge_data(self, **overrides):
        return {'org': self.org.pk, 'badge': self.badge.badge, 'description': '消息翻译',
                'url': '', 'contact': '', **overrides}

    def profile_data(self, **overrides):
        return {'primaryemail': self.holder.email, 'first_name': '小明', 'last_name': '张', **overrides}

    def test_chinese_slug_is_stable_when_badge_is_renamed(self):
        self.assertEqual(self.badge.slug, '中文翻译贡献者')
        form = BadgeForm(instance=self.badge, data=self.badge_data(badge='中文翻译志愿者'))
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.badge.refresh_from_db()
        self.assertEqual(self.badge.badge, '中文翻译志愿者')
        self.assertEqual(self.badge.slug, '中文翻译贡献者')
        self.assertContains(self.client.get('/community/badge/中文翻译贡献者/'), '中文翻译志愿者')

    def test_invalid_or_colliding_slug_rejected_in_form(self):
        for name in ('!!!', '中文翻译贡献者！'):
            form = BadgeForm(data=self.badge_data(badge=name))
            self.assertFalse(form.is_valid())
            self.assertIn('badge', form.errors)

    def test_public_pages_only_show_approved_badges_and_opted_in_people(self):
        hidden = Badge.objects.create(org=self.org, badge='待审核徽章')
        self.assertContains(self.client.get('/community/people/'), self.badge.badge)
        self.assertNotContains(self.client.get('/community/people/'), hidden.badge)
        for suffix in ('', 'image/'):
            self.assertEqual(self.client.get('/community/badge/{}/{}'.format(hidden.slug, suffix)).status_code, 404)
        self.assertEqual(self.client.get('/community/people/holder/').status_code, 404)
        response = self.client.get('/community/badge/{}/'.format(self.badge.slug))
        self.assertNotContains(response, '/community/people/holder/')
        self.assertNotContains(response, self.holder.email)
        Contributor.objects.create(user=self.holder, firstname='小明', lastname='张')
        self.assertContains(self.client.get('/community/badge/{}/'.format(self.badge.slug)), '/community/people/holder/')
        self.assertNotContains(self.client.get('/community/people/holder/'), self.holder.email)

    def test_profile_requires_badge_and_explicit_opt_in_without_publishing_login_email(self):
        self.client.force_login(self.holder)
        self.assertEqual(self.client.post('/account/profile/', self.profile_data()).status_code, 302)
        self.assertFalse(Contributor.objects.filter(user=self.holder).exists())
        response = self.client.post('/account/profile/', self.profile_data(create_contributor_profile='on'))
        self.assertEqual(response.status_code, 302)
        contributor = Contributor.objects.get(user=self.holder)
        self.assertFalse(contributor.email)
        response = self.client.post('/account/profile/', self.profile_data(
            create_contributor_profile='on', firstname='小明', lastname='张', contribution='参与翻译'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Contributor.objects.filter(user=self.holder).count(), 1)
        self.client.force_login(self.other)
        response = self.client.post('/account/profile/', {
            'primaryemail': self.other.email, 'first_name': '其他', 'last_name': '用户',
            'create_contributor_profile': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Contributor.objects.filter(user=self.other).exists())

    def test_unapproved_badge_does_not_enable_public_profile(self):
        self.badge.approved = False
        self.badge.save()
        self.client.force_login(self.holder)
        self.assertNotContains(self.client.get('/account/profile/'), 'name="create_contributor_profile"')
        self.client.post('/account/profile/', self.profile_data(create_contributor_profile='on'))
        self.assertFalse(Contributor.objects.filter(user=self.holder).exists())

    def test_only_organisation_manager_can_edit_and_award(self):
        url = '/account/badges/{}/'.format(self.badge.pk)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, self.badge_data(add_holder=self.other.email)).status_code, 403)
        self.assertEqual(self.badge.holders.count(), 1)
        response = self.client.post('/account/badges/new/', self.badge_data(badge='无权限徽章'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Badge.objects.filter(badge='无权限徽章').exists())
        self.client.force_login(self.manager)
        response = self.client.post(url, self.badge_data(add_holder=self.other.email))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.badge.holders.filter(pk=self.other.pk).exists())

    def test_new_badge_is_submitted_with_image_and_waits_for_approval(self):
        self.client.force_login(self.manager)
        response = self.client.post('/account/badges/new/', self.badge_data(
            badge='社区会议讲者', imagedata=SimpleUploadedFile('badge.png', image_bytes())))
        self.assertRedirects(response, '/account/edit/badges/')
        badge = Badge.objects.get(badge='社区会议讲者')
        self.assertEqual(badge.slug, '社区会议讲者')
        self.assertFalse(badge.approved)
        self.assertEqual(Image.open(io.BytesIO(bytes(badge.imagedata))).size, (150, 150))
        self.assertEqual(self.client.get('/community/badge/社区会议讲者/').status_code, 404)
        self.assertContains(self.client.get('/account/'), '社区会议讲者')

    def test_upload_keep_clear_and_conflicting_file_inputs(self):
        self.client.force_login(self.manager)
        url = '/account/badges/{}/'.format(self.badge.pk)
        response = self.client.get(url)
        self.assertContains(response, 'enctype="multipart/form-data"')
        raw = image_bytes()
        response = self.client.post(url, self.badge_data(imagedata=SimpleUploadedFile('badge.png', raw)))
        self.assertEqual(response.status_code, 302)
        self.badge.refresh_from_db()
        stored = bytes(self.badge.imagedata)
        self.assertEqual(Image.open(io.BytesIO(stored)).size, (150, 150))
        self.assertEqual(self.client.post(url, self.badge_data()).status_code, 302)
        self.badge.refresh_from_db()
        self.assertEqual(bytes(self.badge.imagedata), stored)
        response = self.client.post(url, self.badge_data(**{
            'imagedata': SimpleUploadedFile('badge.png', raw), 'imagedata-clear': 'on'}))
        self.assertContains(response, '不能同时上传新图片')
        self.badge.refresh_from_db()
        self.assertEqual(bytes(self.badge.imagedata), stored)
        self.assertEqual(self.client.post(url, self.badge_data(**{'imagedata-clear': 'on'})).status_code, 302)
        self.badge.refresh_from_db()
        self.assertFalse(self.badge.imagedata)

    def test_badge_image_content_type_etag_and_approval(self):
        raw = image_bytes()
        self.badge.imagedata = raw
        self.badge.save()
        url = '/community/badge/{}/image/'.format(self.badge.slug)
        response = self.client.get(url)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertEqual(response.content, raw)
        self.assertEqual(self.client.get(url, HTTP_IF_NONE_MATCH=response['ETag']).status_code, 304)
        self.badge.approved = False
        self.badge.save()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_retirement_choices_are_scoped_to_this_badge(self):
        other_badge = Badge.objects.create(org=self.org, badge='另一项贡献', approved=True)
        Badgeholder.objects.create(badge=other_badge, user=self.holder, date_retired=date.today())
        form = BadgeForm(instance=self.badge)
        self.assertIn(self.holder, form.fields['retire_holder'].queryset)
        self.assertNotIn(self.holder, form.fields['remove_holder'].queryset)
        form = BadgeForm(instance=other_badge)
        self.assertNotIn(self.holder, form.fields['retire_holder'].queryset)
        self.assertIn(self.holder, form.fields['remove_holder'].queryset)
        forged = BadgeForm(instance=self.badge, data=self.badge_data(remove_holder=[self.holder.pk]))
        self.assertFalse(forged.is_valid())
        self.assertTrue(Badgeholder.objects.filter(pk=self.award.pk).exists())

    def test_retire_reactivate_and_remove_holder(self):
        self.client.force_login(self.manager)
        url = '/account/badges/{}/'.format(self.badge.pk)
        response = self.client.post(url, self.badge_data(retire_holder=[self.holder.pk]))
        self.assertEqual(response.status_code, 302)
        self.award.refresh_from_db()
        self.assertEqual(self.award.date_retired, date.today())
        self.client.post(url, self.badge_data(add_holder=self.holder.email))
        self.award.refresh_from_db()
        self.assertIsNone(self.award.date_retired)
        self.assertEqual(self.client.post(url, self.badge_data(retire_holder=[self.holder.pk])).status_code, 302)
        # The shared submission form limits bursts of more than three edits.
        UserSubmission.objects.filter(user=self.manager).update(when=datetime.now() - timedelta(minutes=11))
        self.assertEqual(self.client.post(url, self.badge_data(remove_holder=[self.holder.pk])).status_code, 302)
        self.assertFalse(Badgeholder.objects.filter(pk=self.award.pk).exists())
