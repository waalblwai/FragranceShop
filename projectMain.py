#!/usr/bin/env python3
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    jsonify,
    url_for,
    flash
    )
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Brand, FragrancesMenu, User

from flask import session as login_session
import random
import string

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secret.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Fragrance Shop App"

# Connect to Database and create database session
engine = create_engine('''sqlite:///brandfragrancesmenuwithusers.db?
                        check_same_thread=False''')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.
                    digits) for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


# VAlIDATE STATE TOKEN.
@app.route('/gconnect', methods=['POST'])
def gconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secret.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('''Current user is already
            connected.'''),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # See if a user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ''' " style = "width: 300px; height: 300px;border-radius:
                150px;-webkit-border-radius: 150px;-moz-border-radius:
                150px;"> '''
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output


# User Helper Functions
def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/gdisconnect')
def gdisconnect():
        # Only disconnect a connected user.
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        # Reset the user's sesson.
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.', 400))
        response.headers['Content-Type'] = 'application/json'
        return response

# ----------------------------------------


# JSON APIs to view Brands Info.
@app.route('/brand/<int:brand_id>/fragrances/JSON')
def BrandMenuJSON(brand_id):
    brand = session.query(Brand).filter_by(id=brand_id).one()
    fragrances = session.query(FragrancesMenu).filter_by(
                brand_id=brand_id).all()
    return jsonify(FragrancesMenu=[f.serialize for f in fragrances])


@app.route('/brand/JSON')
def brandsJSON():
    brands = session.query(Brand).all()
    return jsonify(brands=[b.serialize for b in brands])


# This page will show all my Brands.
@app.route('/')
@app.route('/brand')
def showBrands():
    brands = session.query(Brand).order_by(Brand.name)
    return render_template('brands.html', brands=brands)


# This page will be for making newBrand.
@app.route('/brand/new', methods=['GET', 'POST'])
def newBrand():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        NewBrand = Brand(name=request.form['name'],
                         user_id=login_session['user_id'])
        session.add(NewBrand)
        flash('New Brand %s Successfully Created' % NewBrand.name)
        session.commit()
        return redirect(url_for('showBrands'))
    else:
        return render_template('newbrand.html')


# This page will be for editingBrand.
@app.route('/brand/<int:brand_id>/edit', methods=['GET', 'POST'])
def editingBrand(brand_id):
    toeditebrand = session.query(Brand).filter_by(id=brand_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if toeditebrand.user_id != login_session['user_id']:
        return '''<script>function myFunction() {alert('You are not authorized
                to edit this brand. Please create your own brand in order to
                edit.');}</script><body onload='myFunction()''>'''
    if request.method == 'POST':
        if request.form['name']:
            toeditebrand.name = request.form['name']
            flash('Brand Successfully EDITED %s' % toeditebrand.name)
            return redirect(url_for('showBrands'))
    else:
        return render_template('editingbrand.html', brand=toeditebrand)


# This page will be for deletingBrand.
@app.route('/brand/<int:brand_id>/delete', methods=['GET', 'POST'])
def deletingBrand(brand_id):
    DeletingBrand = session.query(Brand).filter_by(id=brand_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if DeletingBrand.user_id != login_session['user_id']:
        return '''<script>function myFunction() {alert('You are not authorized
                to delete this brand. Please create your own brand in order to
                delete.');}</script><body onload='myFunction()''>'''
    if request.method == 'POST':
        session.delete(DeletingBrand)
        flash('%s Successfully Deleted Brand' % DeletingBrand.name)
        session.commit()
        return redirect(url_for('showBrands', brand_id=brand_id))
    else:
        return render_template('deletingbrand.html', brand=DeletingBrand)


# -----------------------
# CURD for fragrances
# -----------------------
# This page has all brands.
@app.route('/brand/<int:brand_id>/')
@app.route('/brand/<int:brand_id>/fragrances')
def showFragrancesMenu(brand_id):
    brand = session.query(Brand).filter_by(id=brand_id).one()
    creator = getUserInfo(brand.user_id)
    fragrances = session.query(FragrancesMenu).filter_by(
        brand_id=brand_id).all()
    if 'username' not in login_session or creator.id != login_session['user_id']:
        return render_template('publicmenu.html', fragrances=fragrances,
                               brand=brand, creator=creator)
    else:
        return render_template('showfragrancesmenu.html',
                               fragrances=fragrances, brand=brand,
                               creator=creator)


# This page is for making a new fragrances for brands.
@app.route('/brand/<int:brand_id>/fragrances/new', methods=['GET', 'POST'])
def newFragrance(brand_id):
    if 'username' not in login_session:
        return redirect('/login')
    brand = session.query(Brand).filter_by(id=brand_id).one()
    if login_session['user_id'] != brand.user_id:
        return '''<script>function myFunction() {alert('You are not authorized
        to add fragrances to this brand. Please create your own brand in order
        to add fragrances.');}</script><body onload='myFunction()''>'''
    brand = session.query(Brand).filter_by(id=brand_id).one()
    if request.method == 'POST':
        NewFragrance = FragrancesMenu(name=request.form['name'],
                                      description=request.form['description'],
                                      price=request.form['price'],
                                      brandSeason=request.form['brandSeason'],
                                      brand_id=brand_id, user_id=brand.user_id)
        session.add(NewFragrance)
        session.commit()
        flash('New Fragrance %s Successfully Created' % (NewFragrance.name))
        return redirect(url_for('showFragrancesMenu', brand_id=brand_id))
    else:
        return render_template('newfragrance.html', brand_id=brand_id)


# This page is for edit fragrances for brands.
@app.route('/brand/<int:brand_id>/fragrances/<int:fragrance_id>/edit/',
           methods=['GET', 'POST'])
def editFragrance(brand_id, fragrance_id):
    if 'username' not in login_session:
        return redirect('/login')
    brand = session.query(Brand).filter_by(id=brand_id).one()
    EditFragrance = session.query(FragrancesMenu).filter_by(
                                id=fragrance_id).one()
    if login_session['user_id'] != brand.user_id:
        return '''<script>function myFunction() {alert('You are not authorized
                to edit fragrances to this brand. Please create your own brand
                in order to edit fragrances.');}</script><body
                onload='myFunction()''>'''
    if request.method == 'POST':
        if request.form['name']:
            EditFragrance.name = request.form['name']
        if request.form['description']:
            EditFragrance.description = request.form['description']
        if request.form['price']:
            EditFragrance.price = request.form['price']
        if request.form['brandSeason']:
            EditFragrance.brandSeason = request.form['brandSeason']
        session.add(EditFragrance)
        session.commit()
        flash('Fragrance Successfully EDITED!')
        return redirect(url_for('showFragrancesMenu', brand_id=brand_id))
    else:
        return render_template('editfragrance.html',
                               brand_id=brand_id, fragrance_id=fragrance_id,
                               fragrance=EditFragrance)


# This page is for deletingfragrances for brands.
@app.route('/brand/<int:brand_id>/fragrances/<int:fragrance_id>/delete',
           methods=['GET', 'POST'])
def deleteFragrance(brand_id, fragrance_id):
    if 'username' not in login_session:
        return redirect('/login')
    brand = session.query(Brand).filter_by(id=brand_id).one()
    DeleteFragrance = session.query(FragrancesMenu).filter_by(
                                    id=fragrance_id).one()
    if login_session['user_id'] != brand.user_id:
        return '''<script>function myFunction() {alert('You are not authorized
                to delete fragrances to this brand. Please create your own
                brand in order to delete fragrances.');}</script><body
                onload='myFunction()''>'''
    if request.method == "POST":
        session.delete(DeleteFragrance)
        session.commit()
        flash('Fragrance Successfully DELETED!')
        return redirect(url_for('showFragrancesMenu', brand_id=brand_id))
    else:
        return render_template('deletefragrance.html',
                               fragrance=DeleteFragrance)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='0.0.0.0', port=8000)
