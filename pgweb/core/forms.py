from django import forms
from django.forms import ValidationError
from django.conf import settings

from .models import Organisation, OrganisationEmail
from django.contrib.auth.models import User

from pgweb.util.middleware import get_current_user
from pgweb.util.moderation import ModerationState
from pgweb.mailqueue.util import send_simple_mail
from pgweb.util.misc import send_template_mail, generate_random_token


class OrganisationForm(forms.ModelForm):
    new_form_intro = """<em>提示：</em>只有发布新闻、活动、产品或专业服务信息时，才需要创建组织资料。在 PostgreSQL 邮件列表提问或参与讨论、提交 Bug 报告，以及其他一般社区交流，都<em>不需要</em>注册组织。"""

    remove_email = forms.ModelMultipleChoiceField(required=False, queryset=None, label="当前邮箱地址", help_text="选择要移除的一个或多个邮箱地址")
    add_email = forms.EmailField(required=False, label="添加邮箱地址", help_text="输入要添加的邮箱地址")
    remove_manager = forms.ModelMultipleChoiceField(required=False, queryset=None, label="当前管理员", help_text="选择要移除的一个或多个管理员")
    add_manager = forms.EmailField(required=False, label="添加管理员", help_text="输入已注册账户的邮箱地址，将其添加为管理员")

    fieldsets = [
        {
            'id': 'general',
            'legend': '基本信息',
            'description': '',
            'fields': ['name', 'address', 'url', 'orgtype', ],
        },
        {
            'id': 'managers',
            'legend': '管理员',
            'description': '管理员可以使用和修改此组织的资料。添加管理员前，对方需要先注册账户。',
            'fields': ['remove_manager', 'add_manager'],
        },
        {
            'id': 'emails',
            'legend': '邮箱地址',
            'description': '在此登记的邮箱地址可用于发布新闻。如不发布新闻，则无需添加邮箱地址。',
            'fields': ['remove_email', 'add_email'],
        },
    ]

    class Meta:
        model = Organisation
        exclude = ('lastconfirmed', 'approved', 'managers', 'mailtemplate', 'fromnameoverride')
        labels = {
            'name': '组织名称',
            'address': '地址',
            'url': '网站地址',
            'orgtype': '组织类型',
        }

    def __init__(self, *args, **kwargs):
        super(OrganisationForm, self).__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['remove_manager'].queryset = self.instance.managers.all()
        else:
            del self.fields['remove_manager']
            del self.fields['add_manager']
            # remove the managers fieldset
            self.fieldsets = [fs for fs in self.fieldsets if fs['id'] != 'managers']

        if self.instance and self.instance.pk and self.instance.is_approved:
            # Only allow adding/removing emails on orgs that are actually approved
            self.fields['remove_email'].queryset = OrganisationEmail.objects.filter(org=self.instance)
        else:
            del self.fields['remove_email']
            del self.fields['add_email']
            # remove the emails fieldset
            self.fieldsets = [fs for fs in self.fieldsets if fs['id'] != 'emails']

    def clean_add_email(self):
        if self.cleaned_data['add_email']:
            if OrganisationEmail.objects.filter(org=self.instance, address=self.cleaned_data['add_email'].lower()).exists():
                raise ValidationError("此邮箱地址已登记在您的组织下。")
        return self.cleaned_data['add_email']

    def clean_add_manager(self):
        if self.cleaned_data['add_manager']:
            # Something was added as manager - let's make sure the user exists
            try:
                User.objects.get(email=self.cleaned_data['add_manager'].lower())
            except User.DoesNotExist:
                raise ValidationError("未找到使用邮箱 %s 的用户。" % self.cleaned_data['add_manager'])

        return self.cleaned_data['add_manager']

    def clean_remove_manager(self):
        if self.cleaned_data['remove_manager']:
            removecount = 0
            for toremove in self.cleaned_data['remove_manager']:
                if toremove in self.instance.managers.all():
                    removecount += 1

            if len(self.instance.managers.all()) - removecount <= 0:
                raise ValidationError("组织必须至少保留一位管理员。")
        return self.cleaned_data['remove_manager']

    def clean_remove_email(self):
        if self.cleaned_data['remove_email']:
            for e in self.cleaned_data['remove_email']:
                if e.newsarticle_set.exists():
                    raise ValidationError("无法移除曾用于发布新闻的邮箱地址。如需移除，请联系 webmaster@postgresql.org。")
        return self.cleaned_data['remove_email']

    def save(self, commit=True):
        model = super(OrganisationForm, self).save(commit=False)

        ops = []
        if self.cleaned_data.get('add_email', None):
            # Create the email record
            e = OrganisationEmail(org=model, address=self.cleaned_data['add_email'].lower(), token=generate_random_token())
            e.save()

            # Send email for confirmation
            send_template_mail(
                settings.NOTIFICATION_FROM,
                e.address,
                "Email address added to postgresql.org organisation",
                'core/org_add_email.txt',
                {
                    'org': model,
                    'email': e,
                },
            )
            ops.append('Added email {}, confirmation request sent'.format(e.address))
        if self.cleaned_data.get('remove_email', None):
            for e in self.cleaned_data['remove_email']:
                ops.append('Removed email {}'.format(e.address))
                e.delete()

        if 'add_manager' in self.cleaned_data and self.cleaned_data['add_manager']:
            u = User.objects.get(email=self.cleaned_data['add_manager'].lower())
            model.managers.add(u)
            ops.append('Added manager {}'.format(u.username))
        if 'remove_manager' in self.cleaned_data and self.cleaned_data['remove_manager']:
            for toremove in self.cleaned_data['remove_manager']:
                model.managers.remove(toremove)
                ops.append('Removed manager {}'.format(toremove.username))

        if ops:
            send_simple_mail(
                settings.NOTIFICATION_FROM,
                settings.NOTIFICATION_EMAIL,
                "{0} modified {1}".format(get_current_user().username, model),
                "The following changes were made to {}:\n\n{}".format(model, "\n".join(ops))
            )
        return model

    def apply_submitter(self, model, User):
        model.managers.add(User)


class MergeOrgsForm(forms.Form):
    merge_into = forms.ModelChoiceField(queryset=Organisation.objects.all())
    merge_from = forms.ModelChoiceField(queryset=Organisation.objects.all())

    def clean(self):
        if self.cleaned_data['merge_into'] == self.cleaned_data['merge_from']:
            raise ValidationError("The two organisations selected must be different!")
        return self.cleaned_data


class ModerationForm(forms.Form):
    modnote = forms.CharField(label='Moderation notice', widget=forms.Textarea, required=False,
                              help_text="This note will be sent to the creator of the object regardless of if the moderation state has changed.")
    oldmodstate = forms.CharField(label='Current moderation state', disabled=True)
    modstate = forms.ChoiceField(label='New moderation status', choices=ModerationState.CHOICES + (
        (ModerationState.REJECTED, 'Reject and delete'),
        (ModerationState.BYPASSEMBARGO, '绕过禁发时段并立即发布'),
    ))

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.obj = kwargs.pop('obj')
        self.twostate = hasattr(self.obj, 'approved')

        super().__init__(*args, **kwargs)
        excludestates = [ModerationState.EMBARGOED, ModerationState.BYPASSEMBARGO]
        if self.twostate:
            excludestates.append(ModerationState.PENDING)
        if self.obj.modstate == ModerationState.EMBARGOED:
            excludestates.append(ModerationState.APPROVED)  # Can't re-approve when already approved
            if self.user.is_superuser:
                excludestates.remove(ModerationState.BYPASSEMBARGO)  # Only superusers can bypass embargoes

        self.fields['modstate'].choices = [(k, v) for k, v in self.fields['modstate'].choices if int(k) not in excludestates]

        if self.obj.twomoderators:
            if self.obj.firstmoderator:
                self.fields['modstate'].help_text = 'This object requires approval from two moderators. It has already been approved by {}.'.format(self.obj.firstmoderator)
            else:
                self.fields['modstate'].help_text = 'This object requires approval from two moderators.'

    def clean_modstate(self):
        state = int(self.cleaned_data['modstate'])
        if state == ModerationState.APPROVED and self.obj.twomoderators and self.obj.firstmoderator == self.user:
            raise ValidationError("You already moderated this object, waiting for a *different* moderator")
        return state

    def clean(self):
        cleaned_data = super().clean()

        note = cleaned_data['modnote']

        if note and int(cleaned_data['modstate']) == ModerationState.APPROVED and self.obj.twomoderators and not self.obj.firstmoderator:
            self.add_error('modnote', ("Moderation notices cannot be sent on first-moderator approvals for objects that require two moderators."))

        return cleaned_data


class AdminResetPasswordForm(forms.Form):
    confirm = forms.BooleanField(required=True, label="Confirm that you want to reset this password")
