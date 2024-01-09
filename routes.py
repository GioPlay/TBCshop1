from os import path
from flask import render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy.exc import NoResultFound

from forms import AddProductForm, RegisterForm, EditProductForm, LoginForm
from ext import app, db
from models import Product, ProductCategory, User, CartItem

role = "mod"


@app.route("/")
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)


@app.route("/product/<int:product_id>")
def view_product(product_id):
    chosen_product = Product.query.get(product_id)
    if chosen_product is None:
        return render_template("404.html")
    return render_template("product.html", product=chosen_product, role=role)


@app.route("/search/<string:name>")
def search(name):
    products = Product.query.filter(Product.name.ilike(f"%{name}%")).all()
    return render_template("search.html", products=products)


@app.route("/category/<int:category_id>")
def category(category_id):
    products = Product.query.filter(Product.category_id == category_id).all()
    return render_template("index.html", products=products)


@app.route("/add_product", methods=["POST", "GET"])
def add_product():
    form = AddProductForm()
    form.category.choices = [(category.id, category.name) for category in ProductCategory.query.all()]
    if not current_user.is_authenticated or current_user.role != 'admin':
        return redirect(url_for("/404"))

    if form.validate_on_submit():
        new_product = Product(name=form.name.data, price=form.price.data, img=form.img.data.filename,
                              category_id=form.category.data)

        db.session.add(new_product)
        db.session.commit()

        file_directory = path.join(app.root_path, "static", form.img.data.filename)
        form.img.data.save(file_directory)
        return redirect(url_for('index'))
    return render_template("add_product.html", form=form, )


@app.route("/edit_product/<int:product_id>", methods=["POST", "GET"])
def edit_product(product_id):
    chosen_product = Product.query.get(product_id)
    if not chosen_product:
        return render_template("404.html")

    if not current_user.is_authenticated or current_user.role != 'admin':
        return redirect(url_for("/404"))
    form = EditProductForm()
    form.category.choices = [(category.id, category.name) for category in ProductCategory.query.all()]

    if form.validate_on_submit():
        chosen_product.name = form.name.data
        chosen_product.price = form.price.data
        chosen_product.img = form.img.data.filename
        chosen_product.category = form.category.data

        db.session.commit()

        return redirect(url_for('index'))

    form.name.data = chosen_product.name
    form.price.data = chosen_product.price
    form.img.data = chosen_product.img
    form.category.data = chosen_product.category_id

    return render_template("edit_product.html", form=form, product=chosen_product)


@app.route("/delete_product/<int:product_id>")
def delete_product(product_id):
    if not current_user.is_authenticated or current_user.role != 'admin':
        return redirect(url_for("page_not_found"))

    chosen_product = Product.query.get(product_id)
    if not chosen_product:
        return render_template("404.html")

    db.session.delete(chosen_product)
    db.session.commit()

    return redirect(url_for("index"))


@app.route("/login", methods=["POST", "GET"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(User.username == form.username.data).first()
        if user and user.check_password_hash(form.password.data):
            login_user(user)
            session['user_id'] = user.id
            print(f"User ID in session: {session.get('user_id')}")

            return redirect(url_for("index"))
        else:
            return render_template("login.html", form=form, error="username or password specified incorrectly")

    return render_template("login.html", form=form)


@app.route("/register", methods=["POST", "GET"])
def register():
    form = RegisterForm()
    existing_user = User.query.filter_by(username=form.username.data).first()
    if existing_user:
        flash('a user with the same name is already registered.', 'danger')
        return render_template("register.html", form=form)

    if form.validate_on_submit():
        new_user = User(username=form.username.data, password=form.password.data)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('index'))

    return render_template("register.html", form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route("/404")
def page_not_found():
    return render_template('404.html'), 404


@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    try:
        data = request.get_json()
        product_id = data.get('product_id')

        user = current_user

        cart_item = CartItem.query.filter_by(user_id=user.id, product_id=product_id).first()

        if cart_item:
            cart_item.quantity += 1
        else:
            cart_item = CartItem(product_id=product_id, user_id=user.id, quantity=1)
            db.session.add(cart_item)

        db.session.commit()

        return jsonify({'success': True, 'product_name': cart_item.product.name})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/remove_from_cart', methods=['POST'])
@login_required
def remove_from_cart():
    try:
        user = current_user
        product_id = request.json.get('product_id')
        quantity_to_remove = request.json.get('quantity', 1)

        cart_item = CartItem.query.filter_by(user_id=user.id, product_id=product_id).first()

        if cart_item:
            if cart_item.quantity > quantity_to_remove:
                cart_item.quantity -= quantity_to_remove
            else:
                db.session.delete(cart_item)

            if cart_item.quantity == 0:
                db.session.delete(cart_item)

            db.session.commit()
            return jsonify({'success': True, 'product_name': cart_item.product.name, 'quantity_removed': quantity_to_remove})
        else:
            return jsonify({'success': False, 'error': 'Product not found in user\'s cart'}), 404

    except NoResultFound:
        return jsonify({'success': False, 'error': 'NoResultFound: Product not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/cart')
@login_required
def cart():
    try:
        user = current_user

        cart_items = CartItem.query.filter_by(user_id=user.id).all()

        total_price = sum(item.product.price for item in cart_items)

        return render_template('cart.html', cart_items=cart_items, total_price=total_price)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/get_user_cart', methods=['GET'])
@login_required
def get_user_cart():
    try:
        user = current_user
        cart_items = CartItem.query.filter_by(user_id=user.id).all()
        cart_data = [{'product_name': item.product.name, 'product_price': item.product.price} for item in cart_items]

        return jsonify({'success': True, 'cart': cart_data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(debug=True)
