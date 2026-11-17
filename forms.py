from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Optional, URL, Length
class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    subject = StringField('Subject', validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired()])
class ArticleForm(FlaskForm):
    """Form for submitting new articles"""
    def __init__(self, *args, **kwargs):
        # Get language from kwargs before calling parent's __init__
        lang = kwargs.pop('lang', 'US')
        super().__init__(*args, **kwargs)
        
        # Set default values
        submit_text = 'Submit'
        
        try:
            from ops_svr import g_L10N
            # Get the localization dictionary
            current_loc = g_L10N.get(lang, g_L10N.get('US', {}))
            # Get the submit text, fallback to default if not found
            submit_text = current_loc.get('SUBMIT', 'Submit')
        
            # Store the current localization dictionary
            self.current_loc = {
                'title': current_loc.get('TITLE', 'Title'),
                'content': current_loc.get('CONTENT', 'Content'),
                'author': current_loc.get('AUTHOR', 'Author'),
                'source': current_loc.get('SOURCE', 'Source'),
                'language': current_loc.get('LANGUAGE', 'Language'),
                'source_url': current_loc.get('SOURCE_URL', 'Source URL'),
                'image_url': current_loc.get('IMAGE_URL', 'Image URL'),
                'email': current_loc.get('EMAIL', 'Email'),
                'submit': submit_text
            }
        
            # Update field labels with localized text
            self.title.label.text = self.current_loc['title']
            self.content.label.text = self.current_loc['content']
            self.l10n.label.text = self.current_loc['language']
            self.author.label.text = self.current_loc['author']
            self.source.label.text = self.current_loc['source']
            self.source_url.label.text = self.current_loc['source_url']
            self.image_url.label.text = self.current_loc['image_url']
            self.email.label.text = self.current_loc['email']
            self.submit.label.text = self.current_loc['submit']
        except Exception as e:
            # If anything fails, keep the default 'Submit' text
            import logging
            logging.error(f"Error setting form localization: {str(e)}")
        
        # Set language choices from template context 
        try:
            from ops_svr import get_template_context
            context = get_template_context()
            self.l10n.choices = [(code, code) for code in context['options']]
            # Set default selected language
            self.l10n.default = lang
            self.process()  # This ensures the default is applied
        except Exception as e:
            import logging
            logging.error(f"Error loading language choices: {str(e)}")
            # Fallback to default languages if there's an error
            self.l10n.choices = [('US', 'English'), ('繁中', '繁體中文')]
            self.l10n.default = lang if lang in ['US', '繁中'] else 'US'
            self.process()  # This ensures the default is applied
        
    # Form fields defined at class level
    title = StringField('Title', validators=[
        DataRequired(message='Title is required'),
        Length(min=5, max=200, message='Title must be between 5 and 200 characters')
    ])
    
    content = TextAreaField('Content', validators=[
        DataRequired(message='Content is required'),
        Length(min=20, message='Content must be at least 20 characters')
    ])
    
    l10n = SelectField('Language', choices=[], validators=[DataRequired()])

    author = StringField('Author', validators=[
        DataRequired(message='Please provide your name')
    ])
    
    source = StringField('Source', validators=[
        DataRequired(message='Please provide the source')
    ])
    
    source_url = StringField('Source URL', validators=[
        Optional(),
        URL(message='Please enter a valid URL (e.g., https://example.com)')
    ])
    
    image_url = StringField('Image URL', validators=[
        Optional(),
        URL(message='Please enter a valid image URL')
    ])
    
    email = StringField('Email', validators=[
        DataRequired(message='Email is required and must be a subscriber'),
        Email(message='Please enter a valid email address')
    ])
    
    submit = SubmitField('Submit')  # Default value, will be updated in __init__

    def validate_source_url(self, field):
        """Validate source_url if provided"""
        if field.data and not field.data.startswith(('http://', 'https://')):
            field.data = 'http://' + field.data

    def validate_image_url(self, field):
        """Validate image_url if provided"""
        if field.data and not field.data.startswith(('http://', 'https://')):
            field.data = 'http://' + field.data
        
