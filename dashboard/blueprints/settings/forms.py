from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, PasswordField, SubmitField
from wtforms.validators import DataRequired, URL, Length, NumberRange


class RemoteServerForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(1, 100)])
    url = StringField('Server URL', validators=[DataRequired(), URL()])
    api_key = PasswordField('API Key', validators=[DataRequired(), Length(8, 255)])
    push_interval = IntegerField(
        'Push interval (minutes)',
        validators=[DataRequired(), NumberRange(1, 1440)],
        default=10,
    )
    submit = SubmitField('Save')
