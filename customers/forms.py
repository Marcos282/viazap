#customers/forms.py
from django import forms
from django.contrib.auth.password_validation import validate_password
from customers.models import User
from tenants.models import Tenant
from menu.models import Category    

class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label='Senha', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirme a senha', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ('username', 'email')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Este username já está em uso.')
        if Tenant.objects.filter(subdomain__iexact=username).exists():
            raise forms.ValidationError('Este subdomínio já está em uso.')
        return username

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data['email']).strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Este email já está em uso.')
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("As senhas não coincidem.")
        if password2:
            validate_password(password2, user=User(
                username=self.cleaned_data.get("username", ""),
                email=self.cleaned_data.get("email", ""),
            ))
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user

class UserLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Digite seu email'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Digite sua senha'})
    )


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Digite seu email'})
    )


class SetNewPasswordForm(forms.Form):
    password1 = forms.CharField(
        label='Nova senha',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Digite a nova senha'})
    )
    password2 = forms.CharField(
        label='Confirme a nova senha',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirme a nova senha'})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("As senhas não coincidem.")
        if password2:
            validate_password(password2, user=self.user)
        return password2


class CategoryModelForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'exibir', 'status', 'ordem']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da Categoria'}),
            'exibir': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ordem': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ordem de Exibição'}),
        }