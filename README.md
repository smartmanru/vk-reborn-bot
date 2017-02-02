# Vk bot

##Features

- Sending messages in VK
- Receiving messages from the VK
- Placing likes
- Instant reply
- Approving/creating friend requests

#####Future features:
- Message history
- ...


##Deploy on heroku
```bash
heroku apps:create APP_NAME
heroku git:remote -a APP_NAME

# these addons free
heroku addons:create heroku-redis:hobby-dev
heroku addons:create keen:developer

# environment variables
heroku config:set TOKEN=Telegram-bot-token
heroku config:set APPNAME=APP_NAME
heroku config:set BOT_USERNAME=@your-bot-username
heroku config:set LOG_CHAN=@my-telegram-log-channel
heroku config:set ADMIN_ID=your telegram id(must contain only numbers)

heroku config:set VK_APP_ID=vk app id
heroku config:set VK_LOGIN=vk login
heroku config:set VK_PASS=vk password

git commit -am "commit"
git push heroku master
```

#####Addons setup
Config keys will be automatically added to the environment variables after addons installation. So you do not need to configure anything

#####Check logs
```bash
heroku logs --tail | grep -v router --line-buffered
```

#####Vk authentication
Check line #25 in **main.py** if you have problems
