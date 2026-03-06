from django import forms
from django.contrib.auth import get_user_model
from .models import Product, Rack, Order, CATEGORY_CHOICES, MEASUREMENT_UNIT_CHOICES

User = get_user_model()


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username', 'autofocus': True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))


class AddProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'category',
            'asset_id',
            'item_code',
            'item_name',
            'cabin_name',
            'rack',
            'row_number',
            'column_number',
            'measurement_unit',
            'measurement_value',
            'quantity_available',
            'price',
        ]
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'asset_id': forms.TextInput(attrs={'class': 'form-control'}),
            'item_code': forms.TextInput(attrs={'class': 'form-control'}),
            'item_name': forms.TextInput(attrs={'class': 'form-control'}),
            'cabin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'quantity_available': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'rack': forms.Select(attrs={'class': 'form-control'}),
            'row_number': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'column_number': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'measurement_unit': forms.Select(attrs={'class': 'form-control'}),
            'measurement_value': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2m or 10x5x3'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter rack choices by selected category when possible
        category = None
        if self.data.get('category'):
            category = self.data.get('category')
        elif self.initial.get('category'):
            category = self.initial.get('category')
        if category:
            self.fields['rack'].queryset = Rack.objects.filter(category=category).order_by('rack_number')
        else:
            self.fields['rack'].queryset = Rack.objects.all().order_by('category', 'rack_number')

    def save(self, commit=True):
        obj = super().save(commit=False)
        # Keep a legacy location string in sync for display/search
        parts = []
        if obj.cabin_name:
            parts.append(obj.cabin_name)
        if obj.rack_id and obj.rack and obj.rack.rack_number:
            parts.append(f"Rack {obj.rack.rack_number}")
        if obj.row_number is not None:
            parts.append(f"Row {obj.row_number}")
        if obj.column_number is not None:
            parts.append(f"Col {obj.column_number}")
        obj.location = " / ".join(parts)
        if commit:
            obj.save()
        return obj


class AddRackForm(forms.ModelForm):
    class Meta:
        model = Rack
        fields = ['category', 'cabin_name', 'rack_number', 'rows', 'columns', 'number_of_racks']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'cabin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cabin name'}),
            'rack_number': forms.TextInput(attrs={'class': 'form-control'}),
            'rows': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'columns': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'number_of_racks': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

class IssueRequestForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, initial=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class UploadQuantityForm(forms.Form):
    quantity_added = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class OrderForm(forms.Form):
    quantity_requested = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class OrderFulfillForm(forms.Form):
    quantity_provided = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class AddUserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), min_length=8)
    stage = forms.ChoiceField(choices=[(2, 'Stage 2'), (3, 'Stage 3')], widget=forms.Select(attrs={'class': 'form-control'}))
    full_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    mobile_number = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'full_name', 'mobile_number', 'stage']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class ChangePasswordForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), min_length=8)
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        from django.contrib.auth.password_validation import validate_password
        data = super().clean()
        if not self.user.check_password(data.get('old_password')):
            self.add_error('old_password', 'Incorrect current password.')
        if data.get('new_password1') != data.get('new_password2'):
            self.add_error('new_password2', 'New passwords do not match.')
        if data.get('new_password1'):
            validate_password(data['new_password1'], self.user)
        return data
