from django import forms
from django.contrib.auth import get_user_model
from .models import Product, Rack, Order, CATEGORY_CHOICES, MEASUREMENT_UNIT_CHOICES, ADMIN_SECTION_CHOICES, DEPARTMENT_SECTIONS, DEPARTMENT_CHOICES

User = get_user_model()


class DeletionReasonForm(forms.Form):
    """Form to capture deletion reason when deleting items."""
    deletion_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Please provide a reason for deleting this item...'
        }),
        required=True,
        max_length=500,
        help_text="This reason will be stored in the deleted history for audit purposes."
    )


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
            'asset_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto-generated (GTIIT1, GTIIT2, ...)'}),
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
        # Show all racks (category removed from Rack model)
        self.fields['rack'].queryset = Rack.objects.all().order_by('rack_number')

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
        fields = ['cabin_name', 'rack_number', 'rows', 'columns', 'number_of_racks']
        widgets = {
            'cabin_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cabin name'}),
            'rack_number': forms.TextInput(attrs={'class': 'form-control'}),
            'rows': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'columns': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'number_of_racks': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

class IssueRequestForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reason for this request'}),
    )
    attachment = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'required': False})
    )


class UploadQuantityForm(forms.Form):
    quantity_added = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class OrderForm(forms.Form):
    quantity_requested = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class OrderFulfillForm(forms.Form):
    quantity_provided = forms.IntegerField(min_value=0, widget=forms.NumberInput(attrs={'class': 'form-control'}))


class AddUserForm(forms.ModelForm):
    stage = forms.ChoiceField(choices=[(1, 'Stage 1'), (2, 'Stage 2'), (3, 'Stage 3')], widget=forms.Select(attrs={'class': 'form-control'}), initial=3)
    mobile_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    full_name = forms.CharField(max_length=200, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter full name'}))
    department = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': True})
    )
    section = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': True})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'full_name', 'mobile_number', 'stage', 'department', 'section']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'id': 'username-field'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'id': 'email-field', 'readonly': True}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'placeholder': 'Enter username (will auto-generate email)'
        })
        self.fields['email'].help_text = 'Email will be auto-generated as username@gti.nws.cn'
        self.fields['full_name'].widget.attrs.update({
            'placeholder': 'Enter full name'
        })

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Username already exists. Please choose a different username.')
        return username

    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name')
        if not full_name:
            raise forms.ValidationError('Full name is required.')
        return full_name

    def clean(self):
        cleaned_data = super().clean()
        stage = cleaned_data.get('stage')
        department = cleaned_data.get('department')
        section = cleaned_data.get('section')
        
        # No special validation needed - department and section are optional
        # They will be filled from MSSQL data
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Set email if not provided
        if not user.email and user.username:
            user.email = f"{user.username}@gti.nws.cn"
        
        # Set a default password (can be changed later)
        user.set_password('temp123456')
        
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
