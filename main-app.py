import os,sys,json, datetime
from flask import Flask,render_template,request,session,send_from_directory,redirect,url_for,render_template_string
from flask_socketio import emit, SocketIO
from threading import Thread, Event
from time import sleep
from jinja2 import Template, FileSystemLoader, Environment

################################################
SESSION_SECRET_KEY = '72444c4975fa103866da48ae'
################################################

app = Flask(__name__)
app.secret_key = SESSION_SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] =  datetime.timedelta(days=3)
websocket = SocketIO(app)
CURRENTDIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)

def isRegistered():
    return 'u-name' in session
def submitStatus():
    if isRegistered():
        return SUBMIT_STATUS[session["u-name"]]
    else:
        return False

with open(os.path.join(CURRENTDIR,"config","contestants.json"),"r") as CONTESTANT_CONFIG_FILE:
    CONTESTANT_LIST = json.load(CONTESTANT_CONFIG_FILE)
    CONTESTANT_LIST.insert(0,None)
with open(os.path.join(CURRENTDIR,"config","config.json"),"r") as CONFIG_FILE:
    _temp = json.load(CONFIG_FILE)
    SERVER_PORT=_temp["PORT"]
    DEBUG_MODE=_temp["DEBUG"]
    MMR_DATE = _temp["DATE"]
    TOTAL_JUDGE_NUM = _temp["JUDGENUM"]
    CRITERIA_LIST = _temp["CRITERIA"]
    PALETTE= _temp["PALETTE"]

CRITERIA_SHORT_LIST = []
for i in CRITERIA_LIST:
    CRITERIA_SHORT_LIST.append("".join(i.split("/")[0].split(" ")).lower())

TOTAL_CONTESTANT_NUM =len(CONTESTANT_LIST)-1
TEMPLATE_404 = "404"
TEMPLATE_403 = "403"

CURRENT_CONTESTANT_NUMBER =1

if not os.path.exists(os.path.join(CURRENTDIR,"data","CURRENT-USERS.json")):
    with open(os.path.join(CURRENTDIR,"data","CURRENT-USERS.json"),'w+') as f:
        json.dump([], f, ensure_ascii=False, indent=4)


CURRENT_USER_JSON = open(os.path.join(CURRENTDIR,"data","CURRENT-USERS.json"),'r')
try:
    CURRENT_USERNAME_LIST = [i for i in json.loads(CURRENT_USER_JSON.read())]
except json.decoder.JSONDecodeError:
    CURRENT_USERNAME_LIST = []
CURRENT_USER_JSON.close()
del CURRENT_USER_JSON

SUBMIT_STATUS = {}

for i in CURRENT_USERNAME_LIST:
    SUBMIT_STATUS[i]=os.path.exists(os.path.join(CURRENTDIR,"data",i+".json"))

THREAD = Thread()
EVENT = Event()
RESULT_STATUS = False

# CREATE SCORES.XLSX
class Tabulate(Thread):
    def __init__(self):
        super(Tabulate, self).__init__()
        self.resultHTML = "RESULT"
        self.params = {
            "criteriaList":CRITERIA_LIST,
            "criteriaShort":CRITERIA_SHORT_LIST,
            "totalContestantNum":TOTAL_CONTESTANT_NUM,
            "themeList":THEME_LIST
        }
    def isComplete(self):
        for _username, _status in SUBMIT_STATUS.items():
            if not _status:
                return False
        return True
    def tabulate(self):
        ## Calculate data
        __jsonpath = [os.path.join(CURRENTDIR,"data",i+".json") for i in CURRENT_USERNAME_LIST]
        _scores = []
        _totalAttire = {}
        _averageAttire = {}
        for i in __jsonpath:
            with open(i) as f:
                _scores.append(json.loads(f.read()))
        ## INITIALIZE NESTED OBJECT
        for theme in THEME_LIST:
            _totalAttire[theme]=[]
            _averageAttire[theme]=[]
            for cnum in range(0,TOTAL_CONTESTANT_NUM):
                _totalAttire[theme].append({})
                _averageAttire[theme].append({})
                for gender in ["M","F","A"]:
                    _totalAttire[theme][cnum][gender]={}
                    _averageAttire[theme][cnum][gender]={}
                    for criterion in CRITERIA_SHORT_LIST:
                        _totalAttire[theme][cnum][gender][criterion] = 0;
                        _averageAttire[theme][cnum][gender][criterion] = 0;

        for criterion in CRITERIA_SHORT_LIST:
            for gender in ["M","F"]:
                for theme in THEME_LIST:
                    for cnum in range(0,TOTAL_CONTESTANT_NUM):
                        for i,val in enumerate(CURRENT_USERNAME_LIST):
                            _totalAttire[theme][cnum][gender][criterion] += _scores[i][theme][cnum][gender][criterion];
        for criterion in CRITERIA_SHORT_LIST:
            for gender in ["M","F"]:
                for theme in THEME_LIST:
                    for cnum in range(0,TOTAL_CONTESTANT_NUM):
                        for i,val in enumerate(CURRENT_USERNAME_LIST):
                            _totalAttire[theme][cnum]["A"][criterion] += _scores[i][theme][cnum][gender][criterion];

        for theme in THEME_LIST:
            for cnum in range(0,TOTAL_CONTESTANT_NUM):
                for gender in ["M","F","A"]:
                    for criterion in CRITERIA_SHORT_LIST:
                        _averageAttire[theme][cnum][gender][criterion] =  _totalAttire[theme][cnum][gender][criterion] / TOTAL_JUDGE_NUM
                        
        self.params["averageAttire"]=_averageAttire
        #with open("total.json","w+") as f:
        #    json.dump([_totalAttire,_averageAttire],f,ensure_ascii=False, indent=4)
        ## LOAD TEMPLATE
        __loader = FileSystemLoader(searchpath="./templates")
        __env = Environment(loader=__loader)
        __file = "table.j2"
        _template = __env.get_template(__file)
        self.resultHTML = _template.render(self.params)
        
        ## REDIRECT SITE
        sleep(2)
        websocket.emit('resultsAvailable', None , namespace='/websock')
        global RESULT_STATUS
        RESULT_STATUS = True
        print("SCORES ARE COMPLETE")

    def run(self):
        while not self.isComplete():
            print("SCORES ARE NOT COMPLETE")
            sleep(1)
        self.tabulate()

# INDEX.HTML
@app.route("/")
def index():
    if isRegistered() and not submitStatus():
        return render_template("index.j2", bgColor=PALETTE[3],mmrdate=MMR_DATE, tContestantNum = TOTAL_CONTESTANT_NUM)  
    elif RESULT_STATUS:
        return render_template("table.j2", **THREAD.params)
    elif submitStatus():
        with open(os.path.join(CURRENTDIR,"data",session["u-name"]+".json"),'r') as f:
            return render_template("submitted.j2",username =session["u-name"], jsonContent=json.dumps(f.read(),  ensure_ascii=False, indent=4).replace("\\n","<br>").replace('\\"','"')[1:-1])
    else:
        return render_template("login.j2", error=" ")

# ICON
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(CURRENTDIR, 'static','images'),
                          'favicon.ico',mimetype='image/vnd.microsoft.icon')

# LOGIN VALIDATION
@app.route("/login-validate",methods=['GET','POST'])
def login_validate():
    if request.method == "POST" and not isRegistered():
        _username = request.form['login-username']
        if _username in CURRENT_USERNAME_LIST:
            return render_template("login.j2", error="Username taken!")
        else:
            CURRENT_USERNAME_LIST.append(_username)
            SUBMIT_STATUS[_username] = False
            session.permanent=True
            session['u-name'] = _username
            with open(os.path.join(CURRENTDIR,"data","CURRENT-USERS.json"),'w+') as f:
                 json.dump(CURRENT_USERNAME_LIST, f, ensure_ascii=False, indent=4)
            return render_template("login-validate.j2",username=_username)
    elif request.method == "POST" and isRegistered():
        return "already logged in! <button onClick='location.href=\"http://"+request.host+"/\"'>Redirect</button>"
    else:
        if isRegistered() and not submitStatus():
            return render_template("login-validate.j2",username=session['u-name'])
        else:
            return TEMPLATE_403

# CONTESTANT PAGES
@app.route("/<int:contestantnum>/")
def contestant_route(contestantnum):
    if contestantnum <= TOTAL_CONTESTANT_NUM and contestantnum > 0:
        if isRegistered()and not submitStatus():
            return render_template("contestant-page.j2", criteriaList=CRITERIA_LIST, tContestantNum = TOTAL_CONTESTANT_NUM,contestant=CONTESTANT_LIST[contestantnum], contestantnum=str(contestantnum), contestantdata=(CONTESTANT_LIST[contestantnum]["male"],CONTESTANT_LIST[contestantnum]["female"]))  
        else:
            return TEMPLATE_403
    else:
        return TEMPLATE_404

# AJAX HANDLER FOR SCORE UPLOAD
@app.route("/upload",methods=["POST"])
def handleUpload():
    if isRegistered() and request.method=="POST":
        _formdata = request.form 
        _username = session["u-name"]
        _formdata = json.loads(_formdata["SS"])
        with open(os.path.join(CURRENTDIR,"data",_username+".json"),'w+') as f:
            json.dump(_formdata, f, ensure_ascii=False, indent=4)
        SUBMIT_STATUS[_username]=True
        return "DONE"   
    else:
        return TEMPLATE_403

@app.errorhandler(404)
def page_not_found(e):
    return TEMPLATE_404

if DEBUG_MODE:
    import shutil
    @app.route("/print")
    def print_sessions():
        _temp_string = ""
        print(session)
        print(len(CURRENT_USERNAME_LIST))
        return "printed sessions<br> CURRENT USERS:<br>" +"<br>".join(CURRENT_USERNAME_LIST)
    @app.route("/release")
    def release():
        try:
            _username = session["u-name"]
            session.pop("u-name",None)
            print(CURRENT_USERNAME_LIST)
            if _username in CURRENT_USERNAME_LIST:
                CURRENT_USERNAME_LIST.remove(_username)
            return "released sessions"
        except Exception as e:
            print("ERROR")
            print(e)
            return "failed releasing sessions: ERROR:" + str(e)
    @app.route("/cleardata")
    def cleardata():
        shutil.rmtree(os.path.join(CURRENTDIR,"data"))
        os.mkdir(os.path.join(CURRENTDIR,"data"))
        CURRENT_USERNAME_LIST.clear()
        return "cleared data"
    @app.route("/startThread")
    def startThread():
        THREAD.start()
        return redirect(url_for("/"))
if __name__=="__main__": 
    #if len(CURRENT_USERNAME_LIST) >= TOTAL_JUDGE_NUM and not THREAD.isAlive():
    #    THREAD = Tabulate()
    #    THREAD.start()
    app.run("0.0.0.0",SERVER_PORT, debug=DEBUG_MODE)

#####
"""
    TODO : Already Registered HTML
    TODO : Login Validation HTML
    TODO : TEMPLATE 404 HTML
    TODO : TEMPLATE 403 HTML
    TODO : MAGIC 5 RESULT HTML
    TODO : Q&A HTML
    TODO : NAVIGATION BARS HTML
    TODO : CHANGE SCORE MODAL DESIGN
    TODO : SUMMARY SCORE MODAL DESIGN
    TODO : UPLOAD BUTTON DESIGN
    TODO : INDEX HTML REDESIGN
    TODO : CONTESTANT PAGE MINOR REDESIGN
    TODO : THEME PAGE HTML
    TODO : RESULT HTML FOR DISPLAY
    TODO : MANUAL HTML
    FIXME: TABULATE THREAD
"""
###