import webapp2
import os
import sys
import jinja2
from google.appengine.ext import ndb
from google.appengine.api import users

from tweet_auths import OAuthAccessToken
from tweet_auths import CONSUMER_KEY
from tweet_auths import CONSUMER_SECRET
from TwitterUserObject import TwitterUser
########################################################################
# The following is necessary to make SSL work when running locally
########################################################################

def is_development_server():
    """Use environment variable to test if this is the development
    server.

    """
    return os.environ['APPLICATION_ID'].startswith('dev~')

# See http://stackoverflow.com/a/24066819/500584.
if is_development_server():
    from google.appengine.tools.devappserver2.python import sandbox
    sandbox._WHITE_LIST_C_MODULES += ['_ssl', '_socket']
    # stdlib_socket.py is a local copy of socket.py, since that
    # library is overridden by the AppEngine version.
    import stdlib_socket
    sys.modules['socket'] = stdlib_socket
########################################################################
# End of Hack to make it work locally
########################################################################

import tweepy

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

class MainHandler(webapp2.RequestHandler):
    def get(self):
        template = env.get_template('templates/main.html')
        current_user = users.get_current_user()
        if not current_user:
            self.response.write(template.render({
                'login_url': users.create_login_url('/'),
            }))
        else:
            self.response.write(template.render({
                'logout_url': users.create_logout_url('/'),
            }))


class TweetsPage(webapp2.RequestHandler):

    def get(self):
        # If the user is not authenticated with Google just send them to
        # authenticate with google first.
        current_user = users.get_current_user()
        if not current_user:
            self.redirect(users.create_login_url('/list_tweets'))
            return

        # We need to build the authorization request, it's made of
        # Application keys, which come from the tweet_auths.py, and the
        # access token that we should have already received and stored
        # in datastore.
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        access_token = OAuthAccessToken.query(
                OAuthAccessToken.user_id == current_user.user_id()
                ).get()
        if not access_token:
            # If we don't have an access token yet, send the user to get one.
            # They'll go back to the homepage once they're done.
            self.redirect('/authorize_twitter')
            return
        # Otherwise we're good to go, we can set the access token which we
        # found in datastore, and send our queries to twitter to retrieve the
        # user data.
        auth.set_access_token(access_token.token, access_token.token_secret )

        api = tweepy.API(auth)

        # The following part can be any twitter query that is supported by
        # the tweepy API. In this example we get 10 tweets by Taylor swift.
        stuff = api.user_timeline(
            screen_name = 'taylorswift13',
            count = 10,
            include_rts = True)

        # We'll store the data in a dictionary, and use a template to render
        # it nicely.
        variables = {
            'name': 'taylorswift13',
            'tweets': [status.text for status in stuff]
        }
        template = env.get_template('templates/tweets_list.html')
        self.response.write(template.render(variables))

class FollowersPage(webapp2.RequestHandler):

    def get(self):
        results_template = env.get_template('templates/followers.html')
        current_user = users.get_current_user()
        if not current_user:
            self.redirect(users.create_login_url('/listfollowers'))
            return

        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        access_token = OAuthAccessToken.query(
                OAuthAccessToken.user_id == current_user.user_id()
                ).get()
        if not access_token:
            self.redirect('/authorize_twitter')
            return
        auth.set_access_token(access_token.token, access_token.token_secret )

        api = tweepy.API(auth)
        listoffriends = []
        folks = api.followers()
        for friend in folks:
            listoffriends.append(friend.screen_name)
        listoffriends.append('thehill')
        listoffriends.append('CNN')
        listoffriends.append('BW')
        TwitterUser(name=api.me().screen_name, following=listoffriends, filteredfollowing=[]).put()

        # We'll store the data in a dictionary, and use a template to render
        # it nicely.
        followersform = "<form action='/storeselected', method='get'>"
        checker = TwitterUser.query(TwitterUser.name == api.me().screen_name).get()

        for friend in checker.following:
            followersform += ("<input type='checkbox' name='follower' value=%s>@%s<br>" % (friend, friend))

        followersform += "<input type='submit' value='Submit'></form>"
        template_variables = {'body':followersform, 'username':api.me().screen_name, 'profilepic': api.me().profile_image_url, 'description': api.me().description}
        self.response.out.write(results_template.render(template_variables))

class StoreSelected(webapp2.RequestHandler):
    def get(self):
        selected = self.request.get('follower', allow_multiple=True)
        selectedfollowers = [];
        for followername in selected:
            selectedfollowers.append(followername)
        current_user = users.get_current_user()
        if not current_user:
            self.redirect(users.create_login_url('/list_tweets'))
            return

        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        access_token = OAuthAccessToken.query(
                OAuthAccessToken.user_id == current_user.user_id()
                ).get()
        if not access_token:
            self.redirect('/authorize_twitter')
            return
        auth.set_access_token(access_token.token, access_token.token_secret )

        api = tweepy.API(auth)
        checkname = api.me().screen_name
        changingUser = TwitterUser.query(TwitterUser.name == checkname).get()
        changingUser.filteredfollowing = selectedfollowers
        changingUser.put()
        self.redirect('/filteredtimeline')

class FilteredTimeline(webapp2.RequestHandler):
    def get(self):
        results_template = env.get_template('templates/timeline.html')
        current_user = users.get_current_user()
        auth = tweepy.OAuthHandler(CONSUMER_KEY, CONSUMER_SECRET)
        access_token = OAuthAccessToken.query(OAuthAccessToken.user_id == current_user.user_id()).get()

        if not access_token:
            self.redirect('/authorize_twitter')
            return

        auth.set_access_token(access_token.token, access_token.token_secret)

        api = tweepy.API(auth)

        base_timeline = api.home_timeline()
        new_timeline = []
        checker = api.me().screen_name
        selected = TwitterUser.query(TwitterUser.name == checker).get().filteredfollowing
        for loopstatus in base_timeline:
            if loopstatus.user.screen_name in selected:
                new_timeline.append(loopstatus)

        fillbody = "";

        for tweet in new_timeline:
            fillbody += ("<div class='tweet'> @" + tweet.author.screen_name+": " + tweet.text + "</div>")

        template_variables = {'body':fillbody, 'username':api.me().screen_name, 'profilepic': api.me().profile_image_url, 'description': api.me().description}
        self.response.out.write(results_template.render(template_variables))



app = webapp2.WSGIApplication([
    ('/list_taytay_tweets', TweetsPage),
    ('/listfollowers', FollowersPage),
    ('/filteredtimeline', FilteredTimeline),
    ('/storeselected', StoreSelected),
    ('/', MainHandler)
], debug=True)
