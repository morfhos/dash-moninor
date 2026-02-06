from django import forms

from accounts.models import Cliente
from campaigns.models import Campaign


class LoginForm(forms.Form):
    login = forms.CharField(widget=forms.TextInput(attrs={"class": "input"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "input"}))
    remember = forms.BooleanField(required=False, initial=True)


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nome", "cnpj", "ativo", "logo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "input", "placeholder": "Nome"}),
            "cnpj": forms.TextInput(attrs={"class": "input", "placeholder": "CNPJ"}),
        }


class ClienteUserCreateForm(forms.Form):
    nome = forms.CharField(widget=forms.TextInput(attrs={"class": "input", "placeholder": "Nome"}))
    login = forms.CharField(widget=forms.TextInput(attrs={"class": "input", "placeholder": "Login"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "input", "placeholder": "E-mail"}))
    senha = forms.CharField(widget=forms.PasswordInput(attrs={"class": "input", "placeholder": "Senha"}))


class CampaignWizardForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "start_date", "end_date", "timezone", "media_type", "total_budget"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "placeholder": "Nome da campanha"}),
            "start_date": forms.DateTimeInput(attrs={"class": "input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_date": forms.DateTimeInput(attrs={"class": "input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "timezone": forms.TextInput(attrs={"class": "input", "placeholder": "America/Sao_Paulo"}),
            "media_type": forms.Select(attrs={"class": "input"}),
            "total_budget": forms.NumberInput(attrs={"class": "input", "step": "0.01", "placeholder": "Orçamento total (opcional)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].localize = False
        self.fields["end_date"].localize = False


class CampaignEditForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "start_date", "end_date", "timezone", "media_type", "total_budget", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input", "placeholder": "Nome da campanha"}),
            "start_date": forms.DateTimeInput(attrs={"class": "input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_date": forms.DateTimeInput(attrs={"class": "input", "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "timezone": forms.TextInput(attrs={"class": "input", "placeholder": "America/Sao_Paulo"}),
            "media_type": forms.Select(attrs={"class": "input"}),
            "total_budget": forms.NumberInput(attrs={"class": "input", "step": "0.01", "placeholder": "Orçamento total (opcional)"}),
            "status": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Desabilitar localização para campos datetime-local funcionarem corretamente
        self.fields["start_date"].localize = False
        self.fields["end_date"].localize = False


class ContractUploadForm(forms.Form):
    contract_file = forms.FileField()


class MediaPlanUploadForm(forms.Form):
    xlsx_file = forms.FileField()
    replace_existing = forms.BooleanField(required=False, initial=True)
