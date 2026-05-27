from flask_wtf import FlaskForm
from flask_login import current_user
from wtforms import StringField, PasswordField, SubmitField, HiddenField, SelectField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from ...models import User


class ChangeEmailForm(FlaskForm):
    email = StringField('New email', validators=[DataRequired(), Email()])
    password = PasswordField('Password (to confirm)', validators=[DataRequired()])
    submit = SubmitField('Update email')

    def validate_email(self, field):
        if field.data != current_user.email:
            if User.query.filter_by(email=field.data).first():
                raise ValidationError('Email already registered.')


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current password', validators=[DataRequired()])
    new_password = PasswordField('New password', validators=[DataRequired(), Length(8)])
    confirm_password = PasswordField('Confirm new password', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Change password')


class DeleteAccountForm(FlaskForm):
    password = PasswordField('Confirm your password', validators=[DataRequired()])
    submit = SubmitField('Delete my account', render_kw={'class': 'btn btn-danger w-100 fw-semibold'})


class AdminUserActionForm(FlaskForm):
    user_id = HiddenField(validators=[DataRequired()])
    action = HiddenField(validators=[DataRequired()])
    role = SelectField(
        'Role',
        choices=[('viewer', 'Viewer'), ('editor', 'Editor'), ('admin', 'Admin')]
    )
    submit = SubmitField('Update role')
    delete = SubmitField('Remove')
