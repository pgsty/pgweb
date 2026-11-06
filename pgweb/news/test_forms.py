from unittest.mock import patch

from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.test import TestCase

from pgweb.core.models import Organisation, OrganisationEmail, OrganisationType
from .forms import NewsArticleForm
from .models import NewsTag


class NewsEmailChoiceTests(TestCase):
    def setUp(self):
        for target in ('pgweb.util.signals.send_simple_mail', 'pgweb.util.signals.varnish_purge',
                       'pgweb.util.signals.varnish_purge_xkey'):
            mock = patch(target)
            mock.start()
            self.addCleanup(mock.stop)
        self.manager = User.objects.create_user('news-manager', 'news-manager@example.test')
        self.other = User.objects.create_user('other-manager', 'other-manager@example.test')
        orgtype = OrganisationType.objects.create(typename='用户组')

        def organisation(name, manager, approved=True):
            org = Organisation.objects.create(name=name, orgtype=orgtype, url='https://example.test', approved=approved)
            org.managers.add(manager)
            return org

        self.org_b = organisation('B 组织', self.manager)
        self.org_a = organisation('A 组织', self.manager)
        self.foreign_org = organisation('其他组织', self.other)
        self.pending_org = organisation('待审核组织', self.manager, approved=False)
        self.email_b = OrganisationEmail.objects.create(org=self.org_b, address='news-b@example.test', confirmed=True)
        self.email_a2 = OrganisationEmail.objects.create(org=self.org_a, address='z@example.test', confirmed=True)
        self.email_a1 = OrganisationEmail.objects.create(org=self.org_a, address='a@example.test', confirmed=True)
        self.unconfirmed = OrganisationEmail.objects.create(org=self.org_a, address='unconfirmed@example.test')
        self.foreign_email = OrganisationEmail.objects.create(org=self.foreign_org, address='other@example.test', confirmed=True)
        self.pending_email = OrganisationEmail.objects.create(org=self.pending_org, address='pending@example.test', confirmed=True)
        self.tag = NewsTag.objects.create(urlname='release', name='发布', description='版本发布')

    def form_data(self, **overrides):
        return {'org': self.org_a.pk, 'email': self.email_a1.pk, 'title': '测试新闻',
                'content': '新闻正文。', 'tags': [self.tag.pk], **overrides}

    def test_unfiltered_form_has_no_email_choices_and_keeps_chinese_guidance(self):
        form = NewsArticleForm()
        self.assertEqual(form.fields['email'].label, '回复邮箱')
        self.assertIn('请选择与组织关联且已确认的邮箱地址', form.fields['email'].help_text)
        self.assertTrue(form.fields['email'].required)
        with self.assertNumQueries(0):
            html = BeautifulSoup(str(form['email']), 'html.parser')
        self.assertEqual([option['value'] for option in html.select('option')], [''])

    def test_rendered_options_group_and_sort_only_authorized_confirmed_addresses(self):
        form = NewsArticleForm()
        form.filter_by_user(self.manager)
        with self.assertNumQueries(1):
            html = BeautifulSoup(str(form['email']), 'html.parser')
        groups = html.select('optgroup')
        self.assertEqual([group['label'] for group in groups], ['A 组织', 'B 组织'])
        self.assertEqual([[option.get_text() for option in group.select('option')] for group in groups],
                         [['a@example.test', 'z@example.test'], ['news-b@example.test']])
        self.assertEqual([option['value'] for option in html.select('option')],
                         ['', str(self.email_a1.pk), str(self.email_a2.pk), str(self.email_b.pk)])

    def test_valid_email_remains_selected_and_resolves_to_model(self):
        form = NewsArticleForm(data=self.form_data(email=self.email_a2.pk))
        form.filter_by_user(self.manager)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save(commit=False).email, self.email_a2)
        html = BeautifulSoup(str(form['email']), 'html.parser')
        self.assertEqual(html.select_one('option[selected]')['value'], str(self.email_a2.pk))

    def test_email_must_match_the_selected_organisation(self):
        form = NewsArticleForm(data=self.form_data(email=self.email_b.pk))
        form.filter_by_user(self.manager)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['email'], ['请选择与该组织关联的邮箱地址。'])

    def test_unavailable_or_empty_email_cannot_be_submitted(self):
        for value in (self.unconfirmed.pk, self.foreign_email.pk, self.pending_email.pk, ''):
            with self.subTest(email=value):
                form = NewsArticleForm(data=self.form_data(email=value))
                form.filter_by_user(self.manager)
                self.assertFalse(form.is_valid())
                self.assertIn('email', form.errors)

    def test_user_filtering_is_isolated_between_form_instances(self):
        first = NewsArticleForm()
        first.filter_by_user(self.manager)
        second = NewsArticleForm()
        second.filter_by_user(self.other)
        first_html = BeautifulSoup(str(first['email']), 'html.parser')
        second_html = BeautifulSoup(str(second['email']), 'html.parser')
        self.assertEqual([group['label'] for group in first_html.select('optgroup')], ['A 组织', 'B 组织'])
        self.assertEqual([option['value'] for option in second_html.select('option')], ['', str(self.foreign_email.pk)])
