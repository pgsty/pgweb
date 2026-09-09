from django import forms
from django.core.validators import ValidationError
from django.contrib.auth.forms import AuthenticationForm

import re

from django.contrib.auth.models import User
from pgweb.core.models import UserProfile
from pgweb.contributors.models import Contributor
from .models import SecondaryEmail
from .models import OAUTH_PASSWORD_STORE

from .recaptcha import ReCaptchaField

import logging
log = logging.getLogger(__name__)


def _clean_username(username):
    username = username.lower()

    if not re.match(r'^[a-z0-9\.-]+$', username):
        # XXX: Note! Should we ever allow @ signs in usernames again, we need to also
        #      update util/auth.py and the code for identifying email addresses.
        raise forms.ValidationError("用户名包含无效字符。为兼容第三方软件，只能使用 a-z、0-9、点号（.）和连字符（-）。")
    try:
        User.objects.get(username=username)
    except User.DoesNotExist:
        return username
    raise forms.ValidationError("此用户名已被使用。")


def _clean_email(email):
    email = email.lower()

    if User.objects.filter(email=email).exists():
        raise forms.ValidationError("此邮箱地址已注册。")

    if SecondaryEmail.objects.filter(email=email).exists():
        raise forms.ValidationError("此邮箱地址已关联其他用户。")

    return email


# Override some error handling only in the default authentication form
class PgwebAuthenticationForm(AuthenticationForm):
    def clean(self):
        try:
            return super(PgwebAuthenticationForm, self).clean()
        except ValueError as e:
            if e.message.startswith('Unknown password hashing algorithm'):
                # This is *probably* a user trying to log in with an account that has not
                # been set up properly yet. It could be an actually unsupported hashing
                # algorithm, but we'll deal with that when we get there.
                self._errors["__all__"] = self.error_class(["此账户似乎尚未完成初始化。请先按照注册邮件中的说明完成注册，再尝试登录。"])
                log.warning("User {0} tried to log in with invalid hash, probably because signup was completed.".format(self.cleaned_data['username']))
                return self.cleaned_data
            raise e


class CommunityAuthConsentForm(forms.Form):
    consent = forms.BooleanField(help_text='同意共享上述信息')
    next = forms.CharField(widget=forms.widgets.HiddenInput())

    def __init__(self, orgname, *args, **kwargs):
        self.orgname = orgname
        super(CommunityAuthConsentForm, self).__init__(*args, **kwargs)

        self.fields['consent'].label = '同意向 {0} 提供上述信息'.format(self.orgname)

    def clean(self):
        cleaned_data = super().clean()
        if 'next' not in cleaned_data:
            self.add_error(None, "缺少登录后的跳转地址。")
        if not cleaned_data['next'].startswith('/'):
            self.add_error(None, "登录后的跳转地址无效。")
        return cleaned_data


class SignupForm(forms.Form):
    username = forms.CharField(label='用户名', max_length=30)
    first_name = forms.CharField(label='名字', max_length=30)
    last_name = forms.CharField(label='姓氏', max_length=30)
    email = forms.EmailField(label='邮箱地址')
    email2 = forms.EmailField(label='再次输入邮箱地址')
    captcha = ReCaptchaField(label='验证码')

    def __init__(self, remoteip, *args, **kwargs):
        super(SignupForm, self).__init__(*args, **kwargs)
        self.fields['captcha'].set_ip(remoteip)

    def clean_email2(self):
        # If the primary email checker had an exception, the data will be gone
        # from the cleaned_data structure
        if 'email' not in self.cleaned_data:
            return self.cleaned_data['email2']
        email1 = self.cleaned_data['email'].lower()
        email2 = self.cleaned_data['email2'].lower()

        if email1 != email2:
            raise forms.ValidationError("两次输入的邮箱地址不一致。")
        return email2

    def clean_username(self):
        return _clean_username(self.cleaned_data['username'])

    def clean_email(self):
        return _clean_email(self.cleaned_data['email'])


class SignupOauthForm(forms.Form):
    username = forms.CharField(label='用户名', max_length=30)
    first_name = forms.CharField(label='名字', max_length=30, required=False)
    last_name = forms.CharField(label='姓氏', max_length=30, required=False)
    email = forms.EmailField(label='邮箱地址')
    captcha = ReCaptchaField(label='验证码')

    def __init__(self, *args, **kwargs):
        super(SignupOauthForm, self).__init__(*args, **kwargs)
        self.fields['first_name'].widget.attrs['readonly'] = True
        self.fields['first_name'].widget.attrs['disabled'] = True
        self.fields['last_name'].widget.attrs['readonly'] = True
        self.fields['last_name'].widget.attrs['disabled'] = True
        self.fields['email'].widget.attrs['readonly'] = True
        self.fields['email'].widget.attrs['disabled'] = True

    def clean_username(self):
        return _clean_username(self.cleaned_data['username'])

    def clean_email(self):
        return _clean_email(self.cleaned_data['email'])


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        exclude = ('user',)
        labels = {
            'sshkey': 'SSH 公钥',
            'block_oauth': '禁用 OAuth 登录',
        }
        help_texts = {
            'sshkey': '粘贴 OpenSSH 格式的公钥，每行一个，可填写多个。',
            'block_oauth': '禁止通过 Google、Microsoft 等 OAuth 提供方登录此账户。',
        }

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_block_oauth(self):
        if self.cleaned_data.get('block_oauth', False):
            if self.user.password == OAUTH_PASSWORD_STORE:
                raise ValidationError("此账户通过 OAuth 登录，不能禁用 OAuth。")

        return self.cleaned_data['block_oauth']


class UserForm(forms.ModelForm):
    primaryemail = forms.ChoiceField(choices=[], required=True, label='主要邮箱地址')

    def __init__(self, can_change_email, secondaryaddresses, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        if can_change_email:
            self.fields['primaryemail'].choices = [(self.instance.email, self.instance.email), ] + [(a.email, a.email) for a in secondaryaddresses if a.confirmed]
            if not secondaryaddresses:
                self.fields['primaryemail'].help_text = "如需更改主要邮箱地址，请先在下方将新地址添加为备用邮箱。"
        else:
            self.fields['primaryemail'].choices = [(self.instance.email, self.instance.email), ]
            self.fields['primaryemail'].help_text = "此账户关联了外部认证系统，无法在这里更改主要邮箱地址。"
            self.fields['primaryemail'].widget.attrs['disabled'] = True
            self.fields['primaryemail'].required = False

    class Meta:
        model = User
        fields = ('primaryemail', 'first_name', 'last_name', )
        labels = {
            'first_name': '名字',
            'last_name': '姓氏',
        }


class ContributorForm(forms.ModelForm):
    class Meta:
        model = Contributor
        exclude = ('ctype', 'user', )  # these fields are not user-editable


class AddEmailForm(forms.Form):
    email1 = forms.EmailField(label='新邮箱地址', required=False)
    email2 = forms.EmailField(label='再次输入邮箱地址', required=False)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email1(self):
        email = self.cleaned_data['email1'].lower()

        if email == self.user.email:
            raise forms.ValidationError("这已经是您当前的邮箱地址。")

        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("此邮箱地址已注册。")

        try:
            s = SecondaryEmail.objects.get(email=email)
            if s.user == self.user:
                raise forms.ValidationError("此邮箱地址已关联您的账户。")
            else:
                raise forms.ValidationError("此邮箱地址已注册。")
        except SecondaryEmail.DoesNotExist:
            pass

        return email

    def clean_email2(self):
        # If the primary email checker had an exception, the data will be gone
        # from the cleaned_data structure
        if 'email1' not in self.cleaned_data:
            return self.cleaned_data['email2'].lower()
        email1 = self.cleaned_data['email1'].lower()
        email2 = self.cleaned_data['email2'].lower()

        if email1 != email2:
            raise forms.ValidationError("两次输入的邮箱地址不一致。")
        return email2


class PgwebPasswordResetForm(forms.Form):
    email = forms.EmailField(label='邮箱地址')


class ConfirmSubmitForm(forms.Form):
    confirm = forms.BooleanField(label='确认', required=True, help_text='Confirm')

    def __init__(self, objtype, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['confirm'].help_text = '确认提交这条{}进行审核。'.format(objtype)
