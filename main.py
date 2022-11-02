import os
import stripe
from flask import Flask, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy import PickleType
from sqlalchemy import select
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField
from wtforms.validators import DataRequired, URL
from flask_bootstrap import Bootstrap
from products import sale_items

stripe.api_key = os.getenv("stripe_api_key")



app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("secret_key")

MY_DOMAIN = 'http://127.0.0.1:5000'

# CONNECT TO DB
db = SQLAlchemy()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///commerce.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

Bootstrap(app)
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@login_manager.unauthorized_handler
def unauthorized_handler():
    return redirect(url_for('login'))


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))
    items = relationship('Cart', back_populates="buyer")
    purchases = db.Column(MutableList.as_mutable(PickleType), default=[])


class Products(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    price_id = db.Column(db.String(100))
    product_id = db.Column(db.String(100))
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    features = db.Column(MutableList.as_mutable(PickleType), default=[])


class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    buyer = relationship("User", back_populates='items')
    name = db.Column(db.String(100), unique=True)
    price = db.Column(db.Integer, nullable=False)
    price_id = db.Column(db.String(100))
    product_id = db.Column(db.String(100))


''' 
#Create Database
with app.app_context():
    db.create_all()

# Add products to DB
for i in sale_items:
    new_product = Products(name=i['name'], price_id=i['price_id'], product_id=i['product_id'],
                           description=i['description'], price=i['price'], features=i['features'])

    with app.app_context():
        db.session.add(new_product)
        db.session.commit()
'''


# Forms
class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    name = StringField("Name", validators=[DataRequired()])
    submit = SubmitField("Sign Me Up!")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign Me In!")


@app.context_processor
def utility_processor():
    def items_in_cart():
        return len(current_user.items)

    return dict(items_in_cart=items_in_cart)


@app.route("/")
def home():
    products = db.session.query(Products).all()
    return render_template("index.html", products=products, current_user=current_user)


@app.route('/success')
@login_required
def success():
    # move items to purchases
    for item in current_user.items:
        current_user.purchases.append(item.name)
        db.session.delete(item)
        db.session.commit()
    return render_template('success.html')


@app.route("/cancel")
@login_required
def cancel():
    return render_template("cancel.html")


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():

        if User.query.filter_by(email=form.email.data).first():
            print(User.query.filter_by(email=form.email.data).first())
            # User already exists
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))

        hash_and_salted_password = generate_password_hash(
            form.password.data,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User()
        new_user.email = form.email.data
        new_user.password = hash_and_salted_password
        new_user.name = form.name.data
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for("home"))

    return render_template("register.html", form=form, current_user=current_user)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("That email does not exist. Please try again or Register instead.")
            return redirect(url_for("login"))
        elif not check_password_hash(user.password, password):
            flash("Password incorrect. Please try again.")
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('home'))

    return render_template("login.html", form=form, current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/add-to-cart/<int:item_id>', methods=["GET", "POST"])
@login_required
def add_to_cart(item_id):
    if not current_user.is_authenticated:
        return redirect(url_for('login'))

    item_to_add = Products.query.get(item_id)
    new_cart_item = Cart()
    new_cart_item.buyer = current_user
    new_cart_item.name = item_to_add.name
    new_cart_item.price = item_to_add.price
    new_cart_item.price_id = item_to_add.price_id
    new_cart_item.product_id = item_to_add.product_id
    db.session.add(new_cart_item)
    db.session.commit()
    return redirect(url_for('home'))


@app.route("/show-cart")
@login_required
def show_cart():
    total = 0
    for item in current_user.items:
        total += item.price
    return render_template("cart.html", current_user=current_user, total=total)


@app.route("/delete/<int:item_id>")
@login_required
def delete_cart_item(item_id):
    item_to_delete = Cart.query.get(item_id)
    db.session.delete(item_to_delete)
    db.session.commit()
    return redirect(url_for('show_cart'))


@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    line_items = []
    for item in current_user.items:
        line_items.append(
            {
                'price': item.price_id,
                'quantity': 1
            })

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=line_items,
            mode='payment',
            success_url=MY_DOMAIN + '/success',
            cancel_url=MY_DOMAIN + '/cancel',
        )
    except Exception as e:
        return str(e)

    return redirect(checkout_session.url, code=303)


@app.route("/my-learning")
@login_required
def show_purchases():
    return render_template('my-learning.html', current_user=current_user)


if __name__ == "__main__":
    app.run(debug=True)
