from flask_wtf import FlaskForm
from wtforms import HiddenField
from wtforms.validators import DataRequired


class AdminUserActionForm(FlaskForm):
    user_id = HiddenField(validators=[DataRequired()])
    action = HiddenField(validators=[DataRequired()])
