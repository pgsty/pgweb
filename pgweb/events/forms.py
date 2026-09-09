from django import forms
from django.forms import ValidationError

from pgweb.core.models import Organisation
from .models import Event


class EventForm(forms.ModelForm):
    form_intro = '提交活动前，请先阅读现行的<a href="/about/policies/news-and-events/">新闻与活动收录政策</a>。'

    toggle_fields = [
        {
            'name': 'isonline',
            'invert': True,
            'fields': ['city', 'state', 'country', ]
        },
    ]

    def __init__(self, *args, **kwargs):
        super(EventForm, self).__init__(*args, **kwargs)
        self.fields['startdate'].help_text = '请使用 YYYY-MM-DD 格式'
        self.fields['enddate'].help_text = '请使用 YYYY-MM-DD 格式'

    def filter_by_user(self, user):
        self.fields['org'].queryset = Organisation.objects.filter(managers=user, approved=True)

    def clean(self):
        cleaned_data = super(EventForm, self).clean()
        if not cleaned_data.get('isonline'):
            # Non online events require city and country
            # (we don't require state, since many countries have no such thing)
            if not cleaned_data.get('city'):
                self._errors['city'] = self.error_class(['线下活动必须填写城市。'])
                del cleaned_data['city']
            if not cleaned_data.get('country'):
                self._errors['country'] = self.error_class(['线下活动必须填写国家。'])
                del cleaned_data['country']
        return cleaned_data

    def clean_startdate(self):
        if self.instance.pk and self.instance.approved:
            if self.cleaned_data['startdate'] != self.instance.startdate:
                raise ValidationError("已获批准的活动不能更改日期。")
        return self.cleaned_data['startdate']

    def clean_enddate(self):
        if self.instance.pk and self.instance.approved:
            if self.cleaned_data['enddate'] != self.instance.enddate:
                raise ValidationError("已获批准的活动不能更改日期。")
        if 'startdate' in self.cleaned_data and self.cleaned_data['enddate'] < self.cleaned_data['startdate']:
            raise ValidationError("结束日期不能早于开始日期。")
        return self.cleaned_data['enddate']

    class Meta:
        model = Event
        exclude = ('submitter', 'approved', 'description_for_badged')
        labels = {
            'org': '组织',
            'title': '标题',
            'isonline': '线上活动',
            'city': '城市',
            'state': '州／省',
            'country': '国家',
            'language': '活动语言',
            'badged': '社区活动',
            'startdate': '开始日期',
            'enddate': '结束日期',
            'summary': '摘要',
            'details': '详细信息',
        }
        help_texts = {
            'org': '如果这里没有可选组织，请查看<a href="/account/orglist/">组织列表</a>并联系组织管理员；如未列出管理员，请联系 <a href="mailto:webmaster@postgresql.org">webmaster@postgresql.org</a>。如果您的组织尚未登记，可以<a href="/account/edit/organisations/">创建组织资料</a>。',
            'language': '填写活动的主要语言；如使用多种语言，请在活动说明中注明。',
            'badged': '如果活动符合<a href="/about/policies/conferences/" target="_blank" rel="noopener">社区活动准则</a>并获社区认可，请勾选“社区活动”。',
            'summary': '简要介绍，显示在活动列表页。',
            'details': '完整的活动说明。',
        }
