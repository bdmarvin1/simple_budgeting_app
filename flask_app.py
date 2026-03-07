import flask
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, abort, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash # For password hashing
from werkzeug.utils import secure_filename
from functools import wraps
import os
import secrets
import markdown
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
import re
from dotenv import load_dotenv
import html
from markupsafe import Markup
flask.Markup = Markup  # Monkey patch: Correct the import
from flaskext.markdown import Markdown
from flask_migrate import Migrate  # Import Migrate
import json, requests
import logging
from blueprint import budget_bp

load_dotenv()  # Load environment variables from .env

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24) # Important for form security
Markdown(app, extensions=['tables', 'attr_list', 'extra', 'toc'])  # Initialize Flask-Markdown

# Create a file handler and set the logging level
file_handler = logging.FileHandler('my_app_errors.log')  # Create a file handler
file_handler.setLevel(logging.DEBUG)  # Set the logging level for the file handler
app.logger.addHandler(file_handler)  # Add the handler to the Flask logger


# Email Configuration (Use Environment Variables!)
SENDER_EMAIL = os.environ.get("MAIL_USERNAME")
SENDER_PASSWORD = os.environ.get("MAIL_PASSWORD")
APPSHEET_API_KEY = os.environ.get("APPSHEET_API_KEY")
APPSHEET_API_ENDPOINT = os.environ.get("APPSHEET_API_ENDPOINT")  # Your provided URL
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")  # Your Gmail address

# Database Configuration (Use environment variables)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 3600
}
# Routes that DO NOT need CSRF protection (e.g., login)
ROUTES_WITHOUT_CSRF = [
    'login', 'register',
    'api_get_pages', 'api_create_page', 'api_get_page',
    'api_update_page', 'api_delete_page', 'api_get_categories',
    'api_delete_category', 'api_schema',
    'budget.login', 'budget.add_project', 'budget.update_project',
    'budget.add_time_entry', 'budget.add_recurring', 'budget.delete_recurring',
    'budget.add_asset', 'budget.delete_asset', 'budget.import_csv',
    'budget.save_import', 'budget.add_transaction', 'budget.delete_transaction'
]

db = SQLAlchemy(app)
migrate = Migrate(app, db, directory='mysite/migrations')  # Initialize Migrate
app.register_blueprint(budget_bp, url_prefix='/admin/budget')

class Page(db.Model):
    __tablename__ = 'page'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    nav_label = db.Column(db.String(100))
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    date_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    meta_description = db.Column(db.String(160))
    h1 = db.Column(db.String(200))
    primary_image = db.Column(db.String(200))
    noindex = db.Column(db.Boolean, default=False)
    template = db.Column(db.String(100), default='page.html')
    page_type = db.Column(db.String(50), default='page')
    status = db.Column(db.String(20), default='published') # draft, scheduled, published
    publish_date = db.Column(db.DateTime, default=datetime.utcnow)
    metadata_json = db.Column(db.Text) # Stored as JSON string
    auto_tldr = db.Column(db.Text, nullable=True)  # AI-generated TL;DR
    auto_toc  = db.Column(db.Text, nullable=True)  # Auto-generated TOC HTML

    @property
    def extra_metadata(self):
        if self.metadata_json:
            try:
                return json.loads(self.metadata_json)
            except:
                return {}
        return {}

    @extra_metadata.setter
    def extra_metadata(self, value):
        self.metadata_json = json.dumps(value)

    # Hierarchy
    parent_id = db.Column(db.Integer, db.ForeignKey('page.id'))
    children = db.relationship('Page', backref=db.backref('parent', remote_side=[id]))

    # Foreign key for User
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    author = db.relationship('User', backref='pages')

    # Foreign key for Category
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    category = db.relationship('Category', backref='pages')

    def __repr__(self):
        return f'{self.title}'

    @property
    def url_path(self):
        if self.slug == 'index':
            return '/'
        if self.page_type == 'blog':
            return f'/blog/{self.slug}/'
        parts = []
        current = self
        visited = set()
        while current and current.slug != 'index' and current.id not in visited:
            visited.add(current.id)
            parts.insert(0, current.slug)
            current = current.parent
        return '/' + '/'.join(parts) + '/'

class NavigationItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(200))
    page_id = db.Column(db.Integer, db.ForeignKey('page.id'))
    order = db.Column(db.Integer, default=0)
    parent_id = db.Column(db.Integer, db.ForeignKey('navigation_item.id'))
    children = db.relationship('NavigationItem', backref=db.backref('parent', remote_side=[id]), order_by='NavigationItem.order')

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Where to redirect unauthenticated users

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)  # Add the name field
    password_hash = db.Column(db.String(256), nullable=False)
    api_key = db.Column(db.String(32), unique=True, nullable=True, index=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_api_key(self):
        self.api_key = secrets.token_hex(16)
        return self.api_key

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) # Category name
    slug = db.Column(db.String(100), unique=True, nullable=False) # Category slug

    def __repr__(self):
        return f''

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=session.get('_csrf_token'))

@app.context_processor
def inject_navigation():
    nav_items = NavigationItem.query.filter_by(parent_id=None).order_by(NavigationItem.order).all()
    return dict(nav_items=nav_items)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_csrf_token():
    return os.urandom(32).hex()  # Generate a random, hexadecimal token

@app.before_request
def before_request():
    if request.method == 'POST' and request.endpoint not in ROUTES_WITHOUT_CSRF: # Check if it's a POST and NOT a login route
        token = session.pop('_csrf_token', None)  # Remove the token from the session
        print(f"CSRF Token from session: {token}")
        print(f"CSRF Token from form: {request.form.get('csrf_token')}")
        if not token or token != request.form.get('csrf_token'):
            abort(400) # Abort with 400 Bad Request
    elif request.method == 'GET' and request.endpoint not in ROUTES_WITHOUT_CSRF: # Check if it's a GET and NOT a login route
        if '_csrf_token' not in session: # Check if it exists
            session['_csrf_token'] = os.urandom(32).hex() # If not, create one

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

def escapejs(value):
    """Escape a string for use in JavaScript."""
    if value is None:
        return ""
    return Markup(value).replace('\\', '\\\\').replace("\'", "\\'").replace('\"', '\\\"').replace('\r', '\\r').replace('\n', '\\n')

app.jinja_env.filters['escapejs'] = escapejs  # Register the filter

def resolve_image_url(img_path, page_type=None, external=False):
    if not img_path:
        return ""
    if img_path.startswith('http'):
        return img_path
    if img_path.startswith('/'):
        # Already an absolute path
        if external:
            return request.host_url.rstrip('/') + img_path
        return img_path

    # If it's a legacy filename (no slashes), implement fallback search
    if '/' not in img_path:
        # Search order:
        # 1. static/images/<filename>
        # 2. static/images/<page_type>/<filename>

        if os.path.exists(os.path.join(app.static_folder, 'images', img_path)):
            filename = f"images/{img_path}"
        elif page_type:
            safe_page_type = re.sub(r'[^a-z0-9_-]+', '', page_type.lower())
            if os.path.exists(os.path.join(app.static_folder, 'images', safe_page_type, img_path)):
                filename = f"images/{safe_page_type}/{img_path}"
            else:
                filename = f"images/{img_path}" # Fallback to root images
        else:
            filename = f"images/{img_path}" # Fallback
    else:
        filename = img_path

    try:
        return url_for('static', filename=filename, _external=external)
    except:
        return f"/static/{filename}"

app.jinja_env.filters['resolve_image_url'] = resolve_image_url


def generate_tldr(content, title=None):
    """Call Claude API to generate a 2-3 sentence TL;DR. Returns None on failure or short content."""
    if not content or len(content.strip()) < 200:
        return None
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        app.logger.warning('ANTHROPIC_API_KEY not set; skipping TL;DR generation')
        return None
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=api_key)
        prompt_parts = [
            'Write a 2-3 sentence TL;DR summary of the following web page. '
            'Be concise, capture the key points, and do not begin with "TL;DR".'
        ]
        if title:
            prompt_parts.append(f'\nPage title: {title}')
        prompt_parts.append(f'\n\nContent:\n{content[:4000]}')
        msg = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=200,
            messages=[{'role': 'user', 'content': ''.join(prompt_parts)}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        app.logger.error(f'TL;DR generation failed: {e}')
        return None


def generate_toc(content):
    """Build a flat TOC HTML string from markdown h2/h3/h4 headings. Returns None if < 2 headings."""
    import unicodedata

    def _slugify(text):
        value = unicodedata.normalize('NFKD', text)
        value = re.sub(r'[^\w\s-]', '', value).strip().lower()
        return re.sub(r'[-\s]+', '-', value)

    headings = []
    for line in (content or '').splitlines():
        m = re.match(r'^(#{2,4})\s+(.+?)$', line.strip())
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            headings.append((level, text, _slugify(text)))

    if len(headings) < 2:
        return None

    items = ''.join(
        f'<li class="toc-item toc-h{lvl}"><a href="#{anchor}">{text}</a></li>'
        for lvl, text, anchor in headings
    )
    return f'<ul class="toc-list">{items}</ul>'


@app.route('/category/<slug>/')
def category_posts(slug):
    category = Category.query.filter_by(slug=slug).first_or_404()
    posts = Page.query.filter_by(category_id=category.id).all()
    return render_template('category_posts.html', category=category, posts=posts)

@app.route('/author/<author_id>/')
def author_posts(author_id):
    author = User.query.get_or_404(author_id)
    posts = Page.query.filter_by(user_id=author_id).all()
    return render_template('author_posts.html', author=author, posts=posts)

@app.route('/admin/')
@login_required
def admin():
    app.logger.debug('Admin page accessed')
    return render_template('admin.html')

@app.route('/admin/blog/')
@login_required
def list_blog_posts():
    posts = Page.query.order_by(Page.date_posted.desc()).all()
    return render_template('list_blog_posts.html', posts=posts)

@app.route('/admin/blog/edit/<post_id>', methods=['GET', 'POST'])
@login_required  # Your login required decorator
def edit_blog_post(post_id):
    print(f'Post ID: {post_id}')
    post = Page.query.get_or_404(post_id)
    decoded_content = html.unescape(post.content)

    if request.method == 'POST':
        title = request.form.get('title')
        h1 = request.form.get('h1')
        content = request.form.get('content')
        meta_description = request.form.get('meta_description')
        slug = request.form.get('slug')
        primary_image = request.form.get('primary_image')
        parent_id = request.form.get('parent_id') or None
        template = request.form.get('template') or 'page.html'
        page_type = request.form.get('page_type') or 'page'
        noindex = True if request.form.get('noindex') else False

        if not slug:
            slug = generate_unique_slug(title)

        auto_tldr = request.form.get('auto_tldr', '').strip()
        auto_toc = request.form.get('auto_toc', '').strip()
        metadata_json = request.form.get('metadata_json', '').strip()

        post.title = title
        post.h1 = h1
        post.content = content
        post.meta_description = meta_description
        post.slug = slug
        post.primary_image = primary_image
        post.parent_id = parent_id
        post.template = template
        post.page_type = page_type
        post.noindex = noindex
        post.auto_tldr = auto_tldr if auto_tldr else generate_tldr(content, post.title)
        post.auto_toc  = auto_toc if auto_toc else generate_toc(content)
        post.metadata_json = metadata_json or None

        try:
            db.session.commit()
            flash('Blog post updated successfully!', 'success')
            return redirect(url_for('list_blog_posts'))  # Redirect to your post list page
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating blog post: {e}', 'danger')
            all_pages = Page.query.all()
            return render_template('edit_blog_post.html', post=post, decoded_content=decoded_content, all_pages=all_pages)

    all_pages = Page.query.all()
    return render_template('edit_blog_post.html', post=post, decoded_content=decoded_content, all_pages=all_pages)

@app.route('/admin/blog/delete/<post_id>/', methods=['POST'])
@login_required
def delete_blog_post(post_id):
    post = Page.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    return redirect(url_for('list_blog_posts'))

@app.route('/admin/account/', methods=['GET', 'POST'])
@login_required
def account_settings():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not current_password or not new_password or not confirm_password:
            flash('All password fields are required.', 'danger')
            return render_template('account_settings.html', title="Account Settings")

        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
            return render_template('account_settings.html', title="Account Settings")

        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('account_settings.html', title="Account Settings")

        if current_password == new_password:
            flash('New password cannot be the same as the current password.', 'warning')
            return render_template('account_settings.html', title="Account Settings")

        current_user.set_password(new_password)
        try:
            db.session.commit()
            flash('Password updated successfully!', 'success')
            return redirect(url_for('admin'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating password: {str(e)}', 'danger')

    return render_template('account_settings.html', title="Account Settings")

@app.route('/admin/generate_api_key/', methods=['POST'])
@login_required
def generate_api_key():
    current_user.generate_api_key()
    try:
        db.session.commit()
        flash('New API key generated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error generating API key: {str(e)}', 'danger')
    return redirect(url_for('account_settings'))

@app.route('/admin/users/')
@login_required
def list_users():
    users = User.query.all()
    return render_template('list_users.html', users=users)

@app.route('/admin/users/add/', methods=['GET', 'POST'])
@login_required
def add_new_user():
    if request.method == 'POST':
        username = request.form.get('username')
        name = request.form.get('name') # Added name field
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not username or not name or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('add_new_user.html', title="Add New User")

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('add_new_user.html', title="Add New User", username=username, name=name)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists.', 'danger')
            return render_template('add_new_user.html', title="Add New User", name=name)

        new_user = User(username=username, name=name)
        new_user.set_password(password) # Hashes the password

        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f'User {username} created successfully!', 'success')
            return redirect(url_for('list_users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')

    return render_template('add_new_user.html', title="Add New User")

@app.route('/admin/users/edit/<int:user_id>/', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Update name
        name_changed = False
        if new_name and new_name != user.name:
            user.name = new_name
            name_changed = True

        # Update password if new password is provided
        password_changed = False
        if new_password:
            if not confirm_password:
                flash('Please confirm the new password.', 'warning')
                return render_template('edit_user.html', user=user, title=f"Edit User - {user.username}")
            if new_password == confirm_password:
                user.set_password(new_password) # Assuming set_password method hashes it
                password_changed = True
            else:
                flash('New passwords do not match.', 'danger')
                return render_template('edit_user.html', user=user, title=f"Edit User - {user.username}")

        # Only commit if there were changes
        if name_changed or password_changed:
            try:
                db.session.commit()
                flash('User details updated successfully.', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating user: {str(e)}', 'danger')
        else:
            flash('No changes submitted.', 'info')

        return redirect(url_for('list_users'))

    return render_template('edit_user.html', user=user, title=f"Edit User - {user.username}")

@app.route('/admin/users/delete/<user_id>/', methods=['POST'])
@login_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('list_users'))

@app.route('/admin/navigation/', methods=['GET', 'POST'])
@login_required
def manage_navigation():
    if request.method == 'POST':
        label = request.form.get('label')
        page_id = request.form.get('page_id') or None
        url = request.form.get('url')
        parent_id = request.form.get('parent_id') or None
        order = request.form.get('order') or 0

        new_item = NavigationItem(
            label=label,
            page_id=page_id,
            url=url,
            parent_id=parent_id,
            order=order
        )
        db.session.add(new_item)
        db.session.commit()
        flash('Navigation item added!', 'success')
        return redirect(url_for('manage_navigation'))

    all_pages = Page.query.all()
    return render_template('manage_navigation.html', all_pages=all_pages)

@app.route('/admin/navigation/delete/<int:item_id>/', methods=['POST'])
@login_required
def delete_nav_item(item_id):
    item = NavigationItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Navigation item deleted!', 'success')
    return redirect(url_for('manage_navigation'))

@app.route('/login/', methods=['GET', 'POST'])
def login():
    app.logger.debug('Login page accessed')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('admin'))
        else:
            flash('Invalid username or password')  # Display an error message
            return render_template('login.html') # Re-render the login form with error

    return render_template('login.html')

@app.route('/logout/')
@login_required
def logout():
    app.logger.debug('Logout page accessed')
    logout_user()
    return redirect(url_for('index'))  # Redirect to home page after logout

@app.route('/blog/')
def blog():
    app.logger.debug('Blog page accessed')
    now = datetime.utcnow()
    posts = Page.query.filter(
        Page.page_type == 'blog',
        or_(Page.status == 'published', Page.status == None),
        or_(Page.publish_date <= now, Page.publish_date == None)
    ).order_by(Page.date_posted.desc()).all()
    return render_template('blog.html', posts=posts)

@app.route('/blog/<slug>/')
def blog_post(slug):
    app.logger.debug(f'{slug} blog accessed')
    now = datetime.utcnow()
    post = Page.query.filter(
        Page.slug == slug,
        or_(Page.status == 'published', Page.status == None),
        or_(Page.publish_date <= now, Page.publish_date == None)
    ).first_or_404()
    return render_template('blog_post.html', post=post)

@app.route('/admin/blog/new/', methods=['GET', 'POST'])
@login_required
def new_blog_post():
    if request.method == 'POST':
        title = request.form.get('title')
        h1 = request.form.get('h1')
        content = request.form.get('markdown_content')  # Get the processed Markdown content
        meta_description = request.form.get('meta_description')
        slug = request.form.get('slug')
        primary_image = request.form.get('primary_image')
        parent_id = request.form.get('parent_id') or None
        template = request.form.get('template') or 'page.html'
        page_type = request.form.get('page_type') or 'blog'
        noindex = True if request.form.get('noindex') else False

        if not slug:
            slug = generate_unique_slug(title)

        category_id = request.form.get('category_id') or None
        new_category_name = request.form.get('new_category')

        if new_category_name:
            # Create a new category
            new_category = Category(name=new_category_name, slug=generate_unique_slug(new_category_name))
            db.session.add(new_category)
            try:
                db.session.commit()  # Commit to get the new category's ID
                category_id = new_category.id
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating category: {e}', 'danger')
                return render_template('new_blog_post.html')  # Replace with actual template name if different
        elif not category_id:
            # Handle the case where no category is selected (e.g., assign a default category)
            default_category = Category.query.first()  # Get the first category
            if default_category:
                category_id = default_category.id
            else:
                flash('No category selected and no default category found.', 'danger')
                return render_template('new_blog_post.html')  # Replace with actual template name if different

        new_post = Page(
            title=title,
            h1=h1,
            content=content,
            slug=slug,
            meta_description=meta_description,
            user_id=current_user.id,
            category_id=category_id,
            primary_image=primary_image,
            parent_id=parent_id,
            template=template,
            page_type=page_type,
            noindex=noindex
        )
        new_post.auto_tldr = generate_tldr(content, title)
        new_post.auto_toc  = generate_toc(content)
        try:
            db.session.add(new_post)
            db.session.commit()
            flash('Blog post created successfully!', 'success')
            return redirect(url_for('admin'))  # Replace 'admin' with the actual route name
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating blog post: {e}', 'danger')
            return render_template('new_blog_post.html')  # Replace with actual template name if different

    categories = Category.query.all()
    all_pages = Page.query.all()
    return render_template('new_blog_post.html', categories=categories, all_pages=all_pages)  # Pass categories to the template

def generate_unique_slug(title, base_slug=None):
    if base_slug:
        slug = base_slug
    else:
        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

    original_slug = slug
    counter = 1
    while Page.query.filter_by(slug=slug).first():
        slug = f"{original_slug}-{counter}"
        counter += 1
    return slug

def serialize_page(page, truncate_content=None, format='markdown'):
    content = page.content
    if format == 'html':
        md = markdown.Markdown(extensions=['tables', 'attr_list', 'extra'])
        content = md.convert(content)

    if truncate_content and content:
        content = content[:truncate_content]

    return {
        'id': page.id,
        'title': page.title,
        'h1': page.h1,
        'nav_label': page.nav_label,
        'content': content,
        'slug': page.slug,
        'meta_description': page.meta_description,
        'page_type': page.page_type,
        'status': page.status,
        'publish_date': page.publish_date.isoformat() if page.publish_date else None,
        'date_posted': page.date_posted.isoformat() if page.date_posted else None,
        'date_updated': page.date_updated.isoformat() if page.date_updated else None,
        'metadata': page.extra_metadata,
        'auto_tldr': page.auto_tldr,
        'auto_toc': page.auto_toc,
        'primary_image': page.primary_image,
        'primary_image_url': resolve_image_url(page.primary_image, page_type=page.page_type, external=True),
        'parent_id': page.parent_id,
        'template': page.template,
        'noindex': page.noindex,
        'user_id': page.user_id,
        'category_id': page.category_id,
        'url_path': page.url_path
    }

def resolve_page_by_path(path):
    if not path or path == '/':
        return Page.query.filter_by(slug='index').first()

    parts = path.strip('/').split('/')
    parent_id = None
    page = None
    for part in parts:
        page = Page.query.filter_by(slug=part, parent_id=parent_id).first()
        if not page:
            return None
        parent_id = page.id
    return page

def get_breadcrumbs(page):
    breadcrumbs = []
    current = page
    visited = set()
    while current and current.id not in visited:
        visited.add(current.id)
        breadcrumbs.insert(0, current)
        current = current.parent

    # Always ensure Home is at the beginning if not already there
    home = Page.query.filter_by(slug='index').first()
    if home and (not breadcrumbs or breadcrumbs[0].id != home.id):
        breadcrumbs.insert(0, home)

    return breadcrumbs

@app.route('/submit_contact_form/', methods=['POST'])
def submit_contact_form():
    app.logger.error('Submit Contact Form accessed')
    print("submit contact form accessed")
    try:
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        form_message = request.form.get('message')
        print("step1")
        if not name:
            return jsonify({'success': False, 'message': 'Name is required.'})
        if not phone and not email:
            return jsonify({'success': False, 'message': 'Either phone or email is required.'})

        data = {
            "Action": "Add",
            "Rows": [
                {
                    "Name": name,
                    "Phone": phone,
                    "Email": email,
                    "Message": form_message,
                }
            ]
        }

        app.logger.error(data)

        headers = {
            "ApplicationAccessKey": APPSHEET_API_KEY,
            "Content-Type": "application/json",
        }
        print("Just before requests.post")
        response = requests.post(APPSHEET_API_ENDPOINT, json=data, headers=headers) # json=data sends the data as JSON
        app.logger.error("requests.post completed")
        print("requests.post completed")
        print(f'Status Code: {response.status_code}')
        if response.status_code == 200:
            return jsonify({'success': True, 'message': 'Message saved successfully!'})
        else:
            app.logger.error(f"AppSheet API Error: {response.status_code} - {response.text}")
            try:  # Attempt to parse JSON error message
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", "Unknown error")
                app.logger.error(f"Parsed Error Message: {error_message}")
                return jsonify({'success': False, 'message': f'Error saving message: {error_message}'})
            except (ValueError, json.JSONDecodeError):  # Handle cases where response is not JSON
                return jsonify({'success': False, 'message': f'Error saving message: {response.text}'}) # Return raw response for debugging

    except Exception as e:
        app.logger.critical(f"Error: {e}")
        return jsonify({'success': False, 'message': f'An error occurred. THIS IS NOT A TEST.'})

@app.route('/')
def index():
    app.logger.debug('Index page accessed')
    page = resolve_page_by_path('index')
    if not page:
        # Fallback to static if DB entry doesn't exist yet
        year = datetime.now().year
        return render_template('index.html', year=year)

    if page.status not in [None, 'published'] or (page.publish_date and page.publish_date > datetime.utcnow()):
        abort(404)

    breadcrumbs = get_breadcrumbs(page)
    return render_template(page.template or 'page.html', page=page, post=page, breadcrumbs=breadcrumbs, year=datetime.now().year)

@app.route('/services/')
def services():
    return catch_all('services')

@app.route('/about-us/')
def about_us():
    return catch_all('about-us')

@app.route('/<path:path>/')
def catch_all(path):
    app.logger.debug(f'Catch-all accessed: {path}')
    page = resolve_page_by_path(path)
    if not page:
        abort(404)

    if page.status not in [None, 'published'] or (page.publish_date and page.publish_date > datetime.utcnow()):
        abort(404)

    breadcrumbs = get_breadcrumbs(page)
    return render_template(page.template or 'page.html', page=page, post=page, breadcrumbs=breadcrumbs, year=datetime.now().year)

@app.route('/sitemap.xml')
def sitemap():
    """Dynamically generate sitemap.xml including all database pages."""
    app.logger.debug('Sitemap accessed')

    routes = []

    # System routes (optional, but keep blog and other main areas)
    system_endpoints = ['blog']
    for endpoint in system_endpoints:
        try:
            url = 'https://www.kclocalseo.com' + url_for(endpoint)
            routes.append({"loc": url, "lastmod": datetime.now().strftime("%Y-%m-%d")})
        except:
            pass

    # Database pages
    now = datetime.utcnow()
    pages = Page.query.filter(
        Page.noindex == False,
        or_(Page.status == 'published', Page.status == None),
        or_(Page.publish_date <= now, Page.publish_date == None)
    ).all()
    for page in pages:
        url_path = page.url_path
        if url_path.startswith('//'):
            url_path = url_path[1:]
        url = 'https://www.kclocalseo.com' + url_path
        lastmod = (page.date_updated or page.date_posted or datetime.now()).strftime("%Y-%m-%d")
        routes.append({"loc": url, "lastmod": lastmod})

    return render_template('sitemap.xml', routes=routes), 200, {'Content-Type': 'application/xml'}

@app.route('/robots.txt')
def robots():
    return render_template('robots.txt')

@app.route('/category/')
def blog_category_page():
    return redirect(url_for('blog'))




def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'message': 'Missing or invalid Authorization header'}), 401

        api_key = auth_header.split(' ')[1]
        user = User.query.filter_by(api_key=api_key).first()
        if not user:
            return jsonify({'message': 'Invalid API key'}), 401

        request.api_user = user
        return f(*args, **kwargs)
    return decorated_function

def save_api_image(image_file, page_type):
    if not image_file:
        return None

    # Add unique identifier to avoid overwrites
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    original_filename = secure_filename(image_file.filename)
    name, ext = os.path.splitext(original_filename)
    filename = f"{name}_{timestamp}{ext}"

    # Sanitize page_type to prevent path traversal
    safe_page_type = re.sub(r'[^a-z0-9_-]+', '', page_type.lower())

    # Determine directory: 'images/' for root types, 'images/<type>/' for others
    if safe_page_type in ['page', 'core', '']:
        rel_dir = 'images'
    else:
        rel_dir = f'images/{safe_page_type}'

    directory = os.path.join('mysite/static', rel_dir)
    if not os.path.exists(directory):
        try:
            os.makedirs(directory)
        except Exception as e:
            app.logger.error(f"Failed to create directory {directory}: {e}")
            rel_dir = 'images' # Fallback to root images folder
            directory = os.path.join('mysite/static', rel_dir)

    image_path = os.path.join(directory, filename)
    try:
        image_file.save(image_path)
        app.logger.debug(f"Saved image to {image_path}")
    except Exception as e:
        app.logger.error(f"Failed to save image {image_path}: {e}")
        return None

    # Return path relative to static/ folder (e.g., 'images/blog/photo_123.jpg')
    return f"{rel_dir}/{filename}"

@app.route('/api/pages/', methods=['GET'])
@require_api_key
def api_get_pages():
    query = Page.query

    if request.args.get('slug'):
        query = query.filter(Page.slug == request.args.get('slug'))
    if request.args.get('page_type'):
        query = query.filter(Page.page_type == request.args.get('page_type'))
    if request.args.get('parent_id'):
        query = query.filter(Page.parent_id == request.args.get('parent_id'))
    if request.args.get('user_id'):
        query = query.filter(Page.user_id == request.args.get('user_id'))
    if request.args.get('status'):
        query = query.filter(Page.status == request.args.get('status'))
    if request.args.get('updated_after'):
        try:
            dt = datetime.fromisoformat(request.args.get('updated_after').replace('Z', '+00:00'))
            query = query.filter(Page.date_updated >= dt)
        except:
            pass
    if request.args.get('updated_before'):
        try:
            dt = datetime.fromisoformat(request.args.get('updated_before').replace('Z', '+00:00'))
            query = query.filter(Page.date_updated <= dt)
        except:
            pass
    if request.args.get('author'):
        # Map author (username) to user_id
        author = User.query.filter_by(username=request.args.get('author')).first()
        if author:
            query = query.filter(Page.user_id == author.id)
        else:
            return jsonify([]), 200
    if request.args.get('parent_slug'):
        parent = Page.query.filter_by(slug=request.args.get('parent_slug')).first()
        if parent:
            query = query.filter(Page.parent_id == parent.id)
        else:
            return jsonify([]), 200
    if request.args.get('category'):
        category = Category.query.filter_by(name=request.args.get('category')).first()
        if category:
            query = query.filter(Page.category_id == category.id)
        else:
            return jsonify([]), 200

    pages = query.all()

    format = request.args.get('format', 'markdown')
    return jsonify([serialize_page(p, truncate_content=150, format=format) for p in pages])

@app.route('/api/pages/<int:page_id>/', methods=['GET'])
@require_api_key
def api_get_page(page_id):
    page = Page.query.get_or_404(page_id)
    return jsonify(serialize_page(page, format=request.args.get('format', 'markdown')))

@app.route('/api/pages/', methods=['POST'])
@require_api_key
def api_create_page():
    if request.is_json:
        data = request.json
    else:
        data = request.form

    image_file = request.files.get('image')

    title = data.get('title')
    content = data.get('content')
    page_type = data.get('page_type', 'page')

    if not title or not content:
        return jsonify({'message': 'Title and content are required'}), 400

    if data.get('slug'):
        requested_slug = data.get('slug')
        if Page.query.filter_by(slug=requested_slug).first():
            return jsonify({'message': f"Slug '{requested_slug}' is already in use"}), 409
        slug = requested_slug
    else:
        slug = generate_unique_slug(title)

    category_id = data.get('category_id')
    category_name = data.get('category_name')
    if category_name:
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            category = Category(name=category_name, slug=generate_unique_slug(category_name))
            db.session.add(category)
            db.session.flush()
        category_id = category.id

    image_filename = save_api_image(image_file, page_type) or data.get('primary_image')

    publish_date = None
    if data.get('publish_date'):
        try:
            publish_date = datetime.fromisoformat(data.get('publish_date').replace('Z', '+00:00'))
        except:
            pass

    new_page = Page(
        title=title,
        h1=data.get('h1') or title,
        content=content,
        slug=slug,
        meta_description=data.get('meta_description'),
        user_id=request.api_user.id,
        category_id=category_id,
        primary_image=image_filename,
        parent_id=data.get('parent_id') or None,
        template=data.get('template', 'page.html'),
        page_type=page_type,
        status=data.get('status', 'published'),
        publish_date=publish_date or datetime.utcnow(),
        noindex=str(data.get('noindex')).lower() == 'true'
    )

    metadata = data.get('metadata')
    if metadata:
        if isinstance(metadata, str):
            try:
                new_page.extra_metadata = json.loads(metadata)
            except:
                pass
        elif isinstance(metadata, dict):
            new_page.extra_metadata = metadata

    new_page.auto_tldr = generate_tldr(content, title)
    new_page.auto_toc  = generate_toc(content)

    try:
        db.session.add(new_page)
        db.session.commit()
        return jsonify({
            'message': 'Page created successfully',
            'id': new_page.id,
            'page': serialize_page(new_page, truncate_content=150)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500

@app.route('/api/pages/<int:page_id>/', methods=['PUT', 'PATCH'])
@require_api_key
def api_update_page(page_id):
    page = Page.query.get_or_404(page_id)
    if request.is_json:
        data = request.json
    else:
        data = request.form
    image_file = request.files.get('image')

    content_updated = False
    if 'title' in data:
        page.title = data['title']
        content_updated = True
    if 'h1' in data: page.h1 = data['h1']
    if 'content' in data:
        page.content = data['content']
        content_updated = True

    if content_updated:
        page.auto_tldr = generate_tldr(page.content, page.title)
        page.auto_toc  = generate_toc(page.content)
    if 'meta_description' in data: page.meta_description = data['meta_description']
    if 'slug' in data:
        new_slug = data['slug']
        if new_slug != page.slug:
            conflict = Page.query.filter(Page.slug == new_slug, Page.id != page_id).first()
            if conflict:
                return jsonify({'message': f"Slug '{new_slug}' is already in use"}), 409
            page.slug = new_slug
    if 'template' in data: page.template = data['template']
    if 'page_type' in data: page.page_type = data['page_type']
    if 'noindex' in data: page.noindex = str(data['noindex']).lower() == 'true'
    if 'parent_id' in data: page.parent_id = data['parent_id'] or None
    if 'status' in data: page.status = data['status']
    if 'publish_date' in data:
        try:
            page.publish_date = datetime.fromisoformat(data['publish_date'].replace('Z', '+00:00'))
        except:
            pass

    if 'metadata' in data:
        metadata = data['metadata']
        if isinstance(metadata, str):
            try:
                page.extra_metadata = json.loads(metadata)
            except:
                pass
        elif isinstance(metadata, dict):
            page.extra_metadata = metadata

    if 'category_name' in data:
        category = Category.query.filter_by(name=data['category_name']).first()
        if not category:
            category = Category(name=data['category_name'], slug=generate_unique_slug(data['category_name']))
            db.session.add(category)
            db.session.flush()
        page.category_id = category.id
    elif 'category_id' in data:
        page.category_id = data['category_id'] or None

    if 'primary_image' in data:
        page.primary_image = data['primary_image']

    if image_file:
        page.primary_image = save_api_image(image_file, page.page_type)

    try:
        db.session.commit()
        return jsonify({
            'message': 'Page updated successfully',
            'page': serialize_page(page, truncate_content=150)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500

@app.route('/api/pages/<int:page_id>/', methods=['DELETE'])
@require_api_key
def api_delete_page(page_id):
    page = Page.query.get_or_404(page_id)
    try:
        db.session.delete(page)
        db.session.commit()
        return jsonify({'message': 'Page deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500

@app.route('/api/categories/', methods=['GET'])
@require_api_key
def api_get_categories():
    categories = Category.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'slug': c.slug,
        'page_count': len(c.pages)
    } for c in categories])

@app.route('/api/categories/<int:cat_id>/', methods=['DELETE'])
@require_api_key
def api_delete_category(cat_id):
    category = Category.query.get_or_404(cat_id)
    if category.pages:
        return jsonify({'message': 'Cannot delete category with associated pages'}), 400
    try:
        db.session.delete(category)
        db.session.commit()
        return jsonify({'message': 'Category deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500

@app.route('/api/schema', methods=['GET'])
def api_schema():
    """
    Returns a comprehensive JSON schema of the API for bots and AI agents.
    """
    return jsonify({
        'info': {
            'title': 'KC Local SEO API',
            'version': '1.1.0',
            'description': 'RESTful API for managing blog posts, service area pages, and categories.',
            'base_url': request.host_url.rstrip('/')
        },
        'authentication': {
            'type': 'Bearer Token',
            'header': 'Authorization: Bearer <your_api_key>',
            'description': 'Users can manage API keys in the admin dashboard under Account Settings.'
        },
        'data_models': {
            'Page': {
                'description': 'Represents a blog post, service page, or core site page.',
                'fields': {
                    'id': {'type': 'Integer', 'read_only': True},
                    'title': {'type': 'String(300)', 'required': True, 'description': 'The SEO title of the page.'},
                    'h1': {'type': 'String(200)', 'description': 'The main heading on the page.'},
                    'nav_label': {'type': 'String(100)', 'description': 'Short label for navigation menus.'},
                    'content': {'type': 'Text', 'required': True, 'description': 'Body content (Markdown preferred).'},
                    'slug': {'type': 'String(200)', 'unique': True, 'description': 'URL-friendly identifier. Auto-generated if omitted.'},
                    'meta_description': {'type': 'String(160)', 'description': 'SEO meta description.'},
                    'primary_image': {'type': 'String(200)', 'description': 'Full URI/URL of the featured image (e.g., /static/images/blog/hero_2024.jpg).'},
                    'page_type': {'type': 'String(50)', 'options': ['blog', 'page', 'service_area', 'service', 'core'], 'default': 'page'},
                    'status': {'type': 'String(20)', 'options': ['draft', 'scheduled', 'published'], 'default': 'published'},
                    'publish_date': {'type': 'ISO8601 String', 'description': 'UTC time when the page becomes public.'},
                    'noindex': {'type': 'Boolean', 'default': False, 'description': 'If true, adds noindex tag to the page.'},
                    'template': {'type': 'String(100)', 'default': 'page.html', 'description': 'The Jinja2 template used for rendering.'},
                    'metadata': {'type': 'JSON', 'description': 'Arbitrary key-value store for SEO tracking (e.g. keywords, scores).'},
                    'parent_id': {'type': 'Integer', 'description': 'ID of the parent page for hierarchical URLs.'},
                    'category_id': {'type': 'Integer', 'description': 'ID of the associated Category.'},
                    'user_id': {'type': 'Integer', 'read_only': True, 'description': 'ID of the author.'},
                    'date_posted': {'type': 'ISO8601 String', 'read_only': True},
                    'date_updated': {'type': 'ISO8601 String', 'read_only': True},
                    'url_path': {'type': 'String', 'read_only': True, 'description': 'Calculated absolute URL path.'},
                    'primary_image_url': {'type': 'String', 'read_only': True, 'description': 'Absolute URL to the featured image.'}
                }
            },
            'Category': {
                'fields': {
                    'id': {'type': 'Integer', 'read_only': True},
                    'name': {'type': 'String(100)', 'required': True},
                    'slug': {'type': 'String(100)', 'unique': True}
                }
            },
            'User': {
                'description': 'Information about authors. No public CRUD endpoints.',
                'fields': {
                    'id': {'type': 'Integer'},
                    'username': {'type': 'String(80)'},
                    'name': {'type': 'String(100)'}
                }
            },
            'NavigationItem': {
                'description': 'Links in the site navigation. Managed via admin dashboard.',
                'fields': {
                    'id': {'type': 'Integer'},
                    'label': {'type': 'String(100)'},
                    'url': {'type': 'String(200)', 'description': 'Direct link or relative path.'},
                    'page_id': {'type': 'Integer', 'description': 'Link to an internal Page ID.'},
                    'order': {'type': 'Integer', 'description': 'Sort order (lowest first).'},
                    'parent_id': {'type': 'Integer', 'description': 'ID for nested menus.'}
                }
            }
        },
        'image_handling': {
            'upload_method': 'multipart/form-data',
            'field_name': 'image',
            'storage_logic': 'Images are stored in static/images/ (or static/images/<page_type>/) and renamed with a timestamp.',
            'note': 'Set featured image via: 1. "image" file upload (multipart). 2. "primary_image" string path/URL. File upload wins if both provided. Paths should be relative to static/ or absolute URLs.'
        },
        'endpoints': {
            '/api/pages/': {
                'GET': {
                    'description': 'List pages with advanced filtering.',
                    'filters': {
                        'slug': 'Match specific slug',
                        'page_type': 'Filter by type (e.g. blog, service_area)',
                        'status': 'Filter by status (draft, scheduled, published)',
                        'author': 'Filter by author username',
                        'category': 'Filter by category name',
                        'parent_slug': 'Filter by parent slug',
                        'parent_id': 'Filter by parent page ID',
                        'user_id': 'Filter by author user ID',
                        'updated_after': 'ISO8601 date filter (records updated on or after)',
                        'updated_before': 'ISO8601 date filter (records updated on or before)',
                        'format': 'markdown|html (markdown default). If provided, includes first 150 chars of content.'
                    },
                    'response': 'Returns a list of page objects. Content is truncated to 150 chars.'
                },
                'POST': {
                    'description': 'Create a new page. Automatically resolves slug conflicts.',
                    'content_types': ['application/json', 'multipart/form-data'],
                    'special_fields': {
                        'category_name': 'If provided, the system finds or creates a category with this name.',
                        'metadata': 'Can be a JSON object or stringified JSON.'
                    }
                }
            },
            '/api/pages/<id>/': {
                'GET': {
                    'description': 'Retrieve full details of a page.',
                    'params': {'format': 'markdown|html'}
                },
                'PUT': {
                    'description': 'Update a page. Supports multipart for image replacement.'
                },
                'PATCH': {
                    'description': 'Partially update a page. Supports multipart for image replacement.'
                },
                'DELETE': {
                    'description': 'Permanently delete a page.'
                }
            },
            '/api/categories/': {
                'GET': {'description': 'List all categories and their page counts.'}
            }
        }
    })


if __name__ == '__main__':
    app.run(debug=True)
