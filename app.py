__author__ = 'janehu'


from flask import Flask, render_template, redirect, url_for, request, flash
import flask.ext.login as flask_login
import string
from werkzeug import secure_filename
import pika
import hashlib
import MySQLdb
import redis
import os
import pickle

DEBUG = True



app = Flask(__name__)
app.secret_key = 'janesapplication'
login_manager = flask_login.LoginManager()
login_manager.init_app(app)

hashtag_search = redis.Redis(host='localhost',port=6379,db=0)
frienddb = redis.Redis(host='localhost',port=6379,db=1)

# test db=3; production db=2
similarimdb = redis.Redis(host='localhost',port=6379,db=2)


# This is the path to the upload directory
app.config['UPLOAD_FOLDER'] = '/home/ubuntu/upload_files/project/images/'
# These are the extension that we are accepting to be uploaded
app.config['ALLOWED_EXTENSIONS'] = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

IMAGE_PATH = '/home/ubuntu/upload_files/project/images/'
THUMBNAIL_PATH = '/home/ubuntu/upload_files/project/thumbnail/'

class User(flask_login.UserMixin):
    def __init__(self, username):
        self.id = username
        self.nickname = None
        self.email = None

#    def is_authenticated(self):
#        return True



#  loads the user (basically, creates an instance of the User class from above).
@login_manager.user_loader
def user_loader(username):
   db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
   cursor = db.cursor()
   try:
       query = "SELECT * FROM users WHERE username='{0}'".format(username)
       cursor.execute(query)
       results = cursor.fetchall()

       user = User(username)
       user.nickname = results[0][2]
       user.email = results[0][3]
       print ("success in user_loader")
       return user
   except db.Error, e:
       print "error in loaduser - mysql"
       return



#@login_manager.request_loader
#def request_loader(request):
#    username = request.form.get('username')
#    if username not in users:
#        return

#    user = User()
#    user.id = username

    # DO NOT ever store passwords in plaintext and always compare password
    # hashes using constant-time comparison!
#    user.is_authenticated = request.form['pw'] == users[username]['pw']

#    return user

@app.route('/api/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return '''
        <h1>Please login</h1>
               <form action='login' method='POST'>
                <input type='text' name='username' id='username' placeholder='username'></input>
                <input type='password' name='pw' id='pw' placeholder='password'></input>
                <input type='submit' name='submit'></input>
               </form>
               <p><a href="/api/signup">Click here to register</a></p>
               '''
    username = request.form['username'].encode('utf-8')
    password = request.form['pw'].encode('utf-8')

    if authenticate(username,password):
        flash("Logged in successfully.")
        return redirect(url_for('homepage'))
    return 'Incorrect in username or password, please go back and try again'


def authenticate(username,password):
   db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
   cursor = db.cursor()
   pwhash = hashlib.md5(password).hexdigest()
   print "In authentication: the hashed pasword is {0}; the username is {1}".format(pwhash, username)
   try:
       query = "SELECT * FROM users WHERE username='{0}' AND pwdhash='{1}'".format(username,pwhash)
       cursor.execute(query)
       results = cursor.fetchall()
       if not results:
           return False
       else:
           user = User(username)
           user.nickname = results[0][2]
           user.email = results[0][3]
           flask_login.login_user(user)
           print "User's nickname is {0}, user's email is {1}".format(user.nickname, user.email)
           return True
   except db.Error, e:
       print "error in authentication - mysql"



def register(username,nickname,email,password):
    hashedpw = hashlib.md5(password).hexdigest()
    print hashedpw
    db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
    cursor = db.cursor()
    try:
        adduser_query = "INSERT INTO users (username, nickname,email,pwdhash) VALUES ('{0}','{1}','{2}','{3}')".format(username,nickname,email,hashedpw)
        cursor.execute(adduser_query)
        db.commit()
        print "Registered a new user! Congrats!"
        return True
    except:
        return False

@app.route('/api/signup',methods=['GET','POST'])
def signup():
    if request.method == 'GET':
        return render_template("signup.html")

    username = request.form['username'].encode('utf-8')
    nickname = request.form['nickname'].encode('utf-8')
    email = request.form['email'].encode('utf-8')
    password = request.form['pw'].encode('utf-8')

    if register(username,nickname,email,password):
        flash("Signup successfully.")
        return redirect(url_for('login'))
    else:
        return "Sorry, the username has been used. Please go back and choose another one."


@app.route('/api/logout')
@flask_login.login_required
def logout():
    username = flask_login.current_user.id

    db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
    cursor = db.cursor()
    im_query = "SELECT name FROM images WHERE username='{0}' ORDER BY upload_time DESC".format(username)
    cursor.execute(im_query)
    results = cursor.fetchall()
    cursor.close()
    db.close()
    image_list = [(row[0]) for row in results]

    for item in image_list:
        similarimdb.delete(username +'+'+item)


    flask_login.logout_user()
    flash("Logged out.")
    return redirect(url_for('login'))


@app.route('/api/homepage')
@flask_login.login_required
def homepage():
    print "User is inside home page"
    db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
    cursor = db.cursor()
    username = flask_login.current_user.id
    has_friends = frienddb.exists(username)
    friend_list = ['None']
    if has_friends:
        friendset = frienddb.smembers(username)
        friend_list = [ f for f in friendset ]

    try:
        print "trying to display images"
        im_query = "SELECT image_ID, name, hashtag1 FROM images WHERE username='{0}' ORDER BY upload_time DESC ".format(username)
        cursor.execute(im_query)
        results = cursor.fetchall()
        cursor.close()
        db.close()
        if len(results) > 0:
            image_list = [(row[0],row[1],row[2]) for row in results]
            print image_list

            asyn_similarity(image_list,username)

            return render_template("home.html",user = username, images=image_list , friend_list = friend_list)

        else:
            return render_template("home.html",user= username, images=[('0','no_image','waiting for a image')], friend_list = friend_list )
    except:
        print "not sucesssful in query"
        pass

def asyn_similarity(image_list,username):
#    content = hashtag + '+'+filename
    if len(image_list)<=3:
        return
    key = username +'+'+ image_list[-1][1]
    if similarimdb.exists(key):
        return
    print "In asynsimilar"
    image_message = ''
    for row in image_list:
        image_message += str(row[0])
        image_message += '-'
        image_message += row[1]
        image_message += '-'
        if row[2] == None:
           image_message += ';'
        else:
           image_message += row[2]
           image_message += ';'

    image_message += username

    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='asyn_similarity')
    channel.basic_publish(exchange='', routing_key='asyn_similarity', body=image_message)
    print ("[x] Sent the imagelist %s to MQ" % image_message)
    connection.close()
    return


@app.route('/api/view_profile')
@flask_login.login_required
def view_profile():
    username = flask_login.current_user.id
    email = flask_login.current_user.email
    nickname = flask_login.current_user.nickname
    return render_template("userprofile.html",user = username, email=email, nickname = nickname)


#  given file, return whether it's an allowed type or not
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in app.config['ALLOWED_EXTENSIONS']

@app.route('/api/submit_image',methods = ['POST'])
@flask_login.login_required
def submit_image():
    message = 'Error in uploading images'
    username = flask_login.current_user.id

    if request.method == 'POST':
        file = request.files['image_file']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            asyn_task(filename,username)

            message = "<pre>Your image has been submitted successfully!</pre>"
    flash(message)
    return redirect(url_for('homepage'))

def asyn_task(filename, username):
    content = username + '+' +filename
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()
    channel.queue_declare(queue='asyn_mq')
    channel.basic_publish(exchange='', routing_key='asyn_mq', body=content)
    print ("[x] Sent the image %s to MQ" % content)
    connection.close()
    return


@app.route('/api/view_image',methods=['GET','POST'])
@flask_login.login_required
def view_image():
    id = request.args.get('id')
    username = flask_login.current_user.id
    db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
    cursor = db.cursor()
    try:
        image_query = "SELECT name,hashtag1 FROM images WHERE image_ID={0} AND username='{1}'".format(id,username)
        cursor.execute(image_query)
        result = cursor.fetchone()
        image_name = result[0]
        hash_tag =''
        if result[1] is not None:
           hash_tag = result[1]

        similarset = similarimdb.smembers(username+'+'+image_name)
        has_similar = len(similarset)>0
        similarlist = []
        for img in similarset:
            (simID, simnam, simhashtag) = img.split('+')
            print "simID:{0}, simnam:{1}, simhashtag:{2}".format(simID,simnam,simhashtag)
            similarlist.append( (simID, simnam, simhashtag) )

        if request.method == 'POST':
            hashtag_temp = request.form['hashtag1'].encode('utf-8')
            newhashtag1 = hashtag_temp.lower()

            searchkey_old = hash_tag+ '+' +username
            searchkey_new = newhashtag1 + '+' + username
            if hashtag_search.exists(searchkey_old):
                hashtag_search.delete(searchkey_old)
            if hashtag_search.exists(searchkey_new):
                hashtag_search.delete(searchkey_new)

            change_hashtag_query = "UPDATE images SET hashtag1='{0}' WHERE image_ID = {1}".format(newhashtag1,id)
            cursor.execute(change_hashtag_query)
            db.commit()
            return render_template("viewitem.html",id = id,user = username, imagename = image_name,hashtag = newhashtag1, similarlist = similarlist , has_similar = has_similar)

        cursor.close()
        db.close()
        if len(result) > 0:

            return render_template("viewitem.html",id =id ,user = username, imagename = image_name,hashtag = hash_tag, similarlist = similarlist , has_similar = has_similar)
        else:
            return "<pre>Sorry, the original image has been deleted.</pre>"
    except:
        "<pre>Sorry, the original image has been deleted.</pre>"



@app.route('/api/delete',methods=['GET','POST'])
@flask_login.login_required
def delete():

    id = request.args.get('id')
    username = flask_login.current_user.id
    db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
    cursor = db.cursor()
    if request.method == 'POST':
        search_query = "SELECT name FROM images WHERE image_ID = {0}".format(id)
        cursor.execute(search_query)
        result = cursor.fetchone()
        image_name = result[0]
        searchkey = image_name + '+' + username
        if hashtag_search.exists(searchkey):
            hashtag_search.delete(searchkey)
        delete_query = "DELETE FROM images WHERE image_ID = {0}".format(id)
        cursor.execute(delete_query)
        db.commit()
    return redirect(url_for('homepage'))


@app.route('/api/search',methods=['GET','POST'])
@flask_login.login_required
def search():
    username = flask_login.current_user.id

    if request.method == 'POST':
        key_hashtag = request.form['search_item'].encode('utf-8')

        searchkey = key_hashtag+ '+' +username
        if hashtag_search.exists(searchkey):
            image_list = get_value(hashtag_search, searchkey)
            return render_template("searchresult.html",user = username, images=image_list)
        else:
            db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
            cursor = db.cursor()
            search_query = "SELECT image_ID,name,username,hashtag1 FROM images WHERE hashtag1='{0}'AND username='{1}' ORDER BY upload_time DESC".format(key_hashtag,username)
            cursor.execute(search_query)
            result = cursor.fetchall()
            cursor.close()
            db.close()
            if len(result)>0:
                image_list = [(row[0],row[1],row[2],row[3]) for row in result]
                set_value(hashtag_search,searchkey,image_list)
                print image_list
                return render_template("searchresult.html",user = username, images=image_list) # 0:image_ID, 1:imagename, 2:username, 3:hashtag1

            else:
                return render_template("searchresult.html",user = username, images=[('0','no_image','no_user','no_hashtag')])
    else:
        return "seems something wrong"



@app.route('/api/find_friend',methods=['GET','POST'])
@flask_login.login_required
def find_friend():
    username = flask_login.current_user.id
    if request.method == 'POST':
        friendname = request.form['friendname'].encode('utf-8')
        db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
        cursor = db.cursor()
        friend_query = "SELECT uid,username,nickname,email FROM users WHERE username='{0}' ".format(friendname)
        cursor.execute(friend_query)
        result = cursor.fetchall()
        cursor.close()
        db.close()
        if len(result)>0:
            friendid = result[0][0]
            friendnickname = result[0][2]
            friendemail = result[0][3]
            is_friend = frienddb.sismember(username,friendname)
            mutualfriendset = frienddb.smembers(username) & frienddb.smembers(friendname)
            has_mutual = len(mutualfriendset)>0
            return render_template("friendprofile.html",user = friendname, email=friendemail, nickname = friendnickname,id = friendid , is_friend = is_friend, mutual = mutualfriendset , has_mutual = has_mutual)
        else:
            return render_template("friendprofile.html",user = 'no one is found', email='no email', nickname = 'no nickname', id = 0, is_friend = False, mutual = set([]), has_mutual = False)
    return


def set_value(redis,key,value):
    redis.set(key,pickle.dumps(value))

def get_value(redis, key):
    pickled_value = redis.get(key)
    if pickled_value is None:
        return None
    return pickle.loads(pickled_value)


@app.route('/api/add_friend',methods=['GET','POST'])
@flask_login.login_required
def add_friend():
    username = flask_login.current_user.id
    if request.method == 'POST':
        friendname = request.args.get('username')

        frienddb.sadd(username,friendname)
    return redirect(url_for('homepage'))

@app.route('/api/friend_home',methods=['GET'])
@flask_login.login_required
def friend_home():
    username = flask_login.current_user.id
    friendname = request.args.get('username')

    db=MySQLdb.connect(host="localhost",user="root",passwd="",db="ierg4080pro",charset="utf8")
    cursor = db.cursor()
    im_query = "SELECT image_ID,name,hashtag1 FROM images WHERE username='{0}' ORDER BY upload_time DESC".format(friendname)
    cursor.execute(im_query)
    results = cursor.fetchall()
    cursor.close()
    db.close()
    if len(results) > 0:
        image_list = [(row[0],row[1],row[2]) for row in results]

        return render_template("friendhome.html", friendname = friendname, images=image_list)
    else:
        return render_template("friendhome.html",friendname = friendname, images=[('0','no_image','waiting for a image')] )


# session-based authentication above. callback for login failures:
@login_manager.unauthorized_handler
def unauthorized_handler():
    return 'Unauthorized'



if __name__ == "__main__":
    app.run(debug = True)




# REFERENCES

# Flask Login:
# https://gist.github.com/bkdinoop/6698956
# http://www.oschina.net/translate/the-flask-mega-tutorial-part-v-user-logins

# RabbitMQ Asynchronous Task:
# http://www.rabbitmq.com/tutorials/tutorial-one-python.html

# Flask Template:
# http://flask.pocoo.org/docs/0.10/templating/

# MySQL Database:
# http://ianhowson.com/a-quick-guide-to-using-mysql-in-python.html

# Image similarity:
# IERG4190 Multimedia Processing Lecture 8
