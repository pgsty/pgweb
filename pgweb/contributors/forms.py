from django import forms
from django.forms import ValidationError
from django.conf import settings

from pgweb.core.models import Organisation
from .models import Contributor, Badge, Badgeholder
from django.contrib.auth.models import User

from pgweb.util.middleware import get_current_user
from pgweb.mailqueue.util import send_simple_mail

from datetime import date


class ContributorModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        contributor = Contributor.objects.filter(user=obj.pk)
        if contributor:
            return f"{obj.first_name} {obj.last_name} ({obj.username}) <{obj.email}>"
        else:
            return f"{obj.first_name} {obj.last_name} ({obj.username}) <{obj.email}>（尚未创建公开档案）"


class BadgeForm(forms.ModelForm):
    form_intro = '贡献徽章用于记录和感谢大家为 PostgreSQL 及其生态投入的时间。组织管理员可以为志愿服务、会议演讲、扩展开发、翻译、答疑或社区活动颁发徽章。徽章审核通过后公开展示；获得者可以自行选择是否创建公开档案。'

    add_holder = forms.CharField(required=False, label='添加获得者', help_text='填写对方在 PGSQL.CC 注册的邮箱地址，多个地址用空格或换行分隔。')
    retire_holder = ContributorModelMultipleChoiceField(required=False, queryset=None, label='当前参与者', help_text='选中已结束参与的成员；其徽章和贡献记录仍会保留。')
    remove_holder = ContributorModelMultipleChoiceField(required=False, queryset=None, label='已结束参与的成员', help_text='选中要移除徽章的成员。如需恢复参与状态，在上方重新添加其邮箱地址即可。')

    fieldsets = [
        {
            'id': 'general',
            'legend': '徽章信息',
            'fields': ['org', 'badge', 'description', 'url', 'imagedata', 'contact', ],
        },
        {
            'id': 'holders',
            'legend': '徽章获得者',
            'fields': ['add_holder', 'retire_holder', 'remove_holder'],
        },
    ]

    class Meta:
        model = Badge
        exclude = ('approved', 'sortorder', 'holders', 'slug',)
        labels = {
            'org': '颁发组织', 'badge': '徽章名称', 'description': '贡献说明',
            'url': '相关链接', 'imagedata': '徽章图片', 'contact': '联系方式',
        }
        help_texts = {
            'org': '选择您管理的组织；组织资料需要先通过审核。',
            'badge': '例如“2026 PostgreSQL 会议讲者”或“中文消息翻译贡献者”，最多 32 个字符。',
            'description': '说明这枚徽章表彰的贡献或参与的活动。',
            'url': '选填。可填写活动、项目或其他相关页面的地址。',
            'imagedata': '上传不超过 1 MB 的 JPEG 或 PNG 图片，将自动缩放至 150 × 150 像素；留空使用 PostgreSQL 大象标志。',
            'contact': '选填。希望获得此徽章的参与者可通过这个邮箱、网址或其他方式联系组织。',
        }

    def __init__(self, *args, **kwargs):
        super(BadgeForm, self).__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['retire_holder'].queryset = User.objects.filter(
                badgeholder__badge=self.instance, badgeholder__date_retired__isnull=True)
            self.fields['remove_holder'].queryset = User.objects.filter(
                badgeholder__badge=self.instance, badgeholder__date_retired__isnull=False)
        else:
            del self.fields['add_holder']
            del self.fields['retire_holder']
            del self.fields['remove_holder']
            # remove the holders fieldset
            self.fieldsets = [fs for fs in self.fieldsets if fs['id'] != 'holders']

    def clean_add_holder(self):
        if self.cleaned_data['add_holder']:
            for u in self.cleaned_data['add_holder'].split():
                # something was added - let's make sure the user exists
                try:
                    User.objects.get(email=u.lower())
                except User.DoesNotExist:
                    raise ValidationError('未找到邮箱为 %s 的本站账户。' % u)
                except User.MultipleObjectsReturned:
                    raise ValidationError('邮箱 %s 对应多个账户，请联系管理员核对。' % u)

        return self.cleaned_data['add_holder']

    def save(self, commit=True):
        badge = super(BadgeForm, self).save(commit=False)
        if commit:
            badge.save()

        ops = []

        if 'add_holder' in self.cleaned_data and self.cleaned_data['add_holder']:
            for u in self.cleaned_data['add_holder'].split():
                user = User.objects.get(email=u.lower())
                holder = Badgeholder.objects.get_or_create(user=user, badge=badge, defaults={'awarded_by': get_current_user()})[0]
                if holder.date_retired:  # un-retire them
                    holder.date_retired = None
                    holder.save()
                    ops.append('恢复 {} 的参与状态'.format(user.username))
                else:
                    ops.append('向 {} 颁发徽章'.format(user.username))
        if 'retire_holder' in self.cleaned_data and self.cleaned_data['retire_holder']:
            for toretire in self.cleaned_data['retire_holder']:
                holder = Badgeholder.objects.get(badge=badge, user=toretire)
                holder.date_retired = date.today()
                holder.save()
                ops.append('将 {} 标记为已结束参与'.format(toretire.username))
        if 'remove_holder' in self.cleaned_data and self.cleaned_data['remove_holder']:
            for toremove in self.cleaned_data['remove_holder']:
                badge.holders.remove(toremove)
                ops.append('移除 {} 的徽章'.format(toremove.username))

        if ops:
            send_simple_mail(
                settings.NOTIFICATION_FROM,
                settings.NOTIFICATION_EMAIL,
                '{} 的获得者列表已更新'.format(badge),
                '{} 的获得者变更：\n\n{}'.format(badge, "\n".join(ops))
            )

        if commit:
            self.save_m2m()
        return badge

    def filter_by_user(self, user):
        self.fields['org'].queryset = Organisation.objects.filter(managers=user, approved=True)
