from django import forms
from django.forms import ValidationError

from pgweb.util.moderation import ModerationState
from pgweb.core.models import Organisation, OrganisationEmail
from .models import NewsArticle, NewsTag


class NewsArticleForm(forms.ModelForm):
    form_intro = '提交新闻前，请先阅读现行的<a href="/about/policies/news-and-events/">新闻与活动收录政策</a>。'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True

    def filter_by_user(self, user):
        self.fields['org'].queryset = Organisation.objects.filter(managers=user, approved=True)
        self.fields['email'].queryset = OrganisationEmail.objects.filter(org__managers=user, org__approved=True, confirmed=True)

    def clean_date(self):
        if self.instance.pk and self.instance.modstate != ModerationState.CREATED:
            if self.cleaned_data['date'] != self.instance.date:
                raise ValidationError("已提交审核或获批准的新闻不能更改日期。")
        return self.cleaned_data['date']

    @property
    def described_checkboxes(self):
        return {
            'tags': {t.id: t.description for t in NewsTag.objects.all()}
        }

    def clean(self):
        data = super().clean()

        if data.get('email', None):
            if data['email'].org != data['org']:
                self.add_error('email', '请选择与该组织关联的邮箱地址。')

        if 'tags' not in data:
            self.add_error('tags', '请选择一个或多个标签。')
        else:
            for t in data['tags']:
                # Check each tag for permissions. This is not very db-efficient, but people
                # don't save news articles that often...
                if t.allowed_orgs.exists() and not t.allowed_orgs.filter(pk=data['org'].pk).exists():
                    self.add_error('tags',
                                   '组织 {} 无权使用标签 {}。'.format(
                                       data['org'],
                                       t,
                                   ))

        return data

    class Meta:
        model = NewsArticle
        exclude = ('date', 'submitter', 'modstate', 'postedto', 'firstmoderator')
        labels = {
            'org': '组织',
            'email': '回复邮箱',
            'title': '标题',
            'content': '正文',
            'tags': '标签',
        }
        help_texts = {
            'org': '如果这里没有可选组织，请查看<a href="/account/orglist/">组织列表</a>并联系组织管理员；如未列出管理员，请联系 <a href="mailto:webmaster@postgresql.org">webmaster@postgresql.org</a>。如果您的组织尚未登记，可以<a href="/account/edit/organisations/">创建组织资料</a>。',
            'email': '请选择与组织关联且已确认的邮箱地址，作为新闻发布后的回复地址。如没有合适的地址，请先在<a href="/account/edit/organisations/">组织资料</a>中添加，再提交新闻。',
            'tags': '选择适合这篇新闻的标签。',
        }
        widgets = {
            'tags': forms.CheckboxSelectMultiple,
        }
