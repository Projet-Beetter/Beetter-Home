from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, NumberRange


class BeehiveForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(1, 100)])
    location = StringField('Location', validators=[Optional(), Length(max=200)])
    device_eui = StringField('Device EUI (LoRa)', validators=[Optional(), Length(max=64)])
    lora_frequency = FloatField(
        'LoRa Frequency (MHz)',
        validators=[Optional(), NumberRange(400, 1000)],
        default=868.0,
    )
    spreading_factor = IntegerField(
        'Spreading Factor (SF7–SF12)',
        validators=[Optional(), NumberRange(7, 12)],
        default=7,
    )
    bandwidth = IntegerField(
        'Bandwidth (kHz)',
        validators=[Optional(), NumberRange(125, 500)],
        default=125,
    )
    submit = SubmitField('Save')
