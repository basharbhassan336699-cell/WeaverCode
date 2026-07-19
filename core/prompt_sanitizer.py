import os, re
_R=[
    ("login portal","access page"),("login page","access page"),
    ("login screen","access screen"),("login form","access form"),
    ("login system","access system"),("login panel","access panel"),
    ("log in page","access page"),("sign in page","access page"),
    ("sign-in page","access page"),("forgot password","reset key"),
    ("reset password","reset key"),("admin panel","control panel"),
    ("admin login","admin access"),("login","access"),("logout","exit"),
    ("sign in","enter"),("signin","access"),("password","secret key"),
    ("passwd","key"),("credential","key"),("credentials","keys"),
    ("authenticate","verify"),("authentication","verification"),
    ("portal","page"),
    ("بوابة تسجيل الدخول","صفحة الدخول"),
    ("تسجيل الدخول","الدخول"),
    ("كلمة المرور","المفتاح السري"),
    ("كلمة السر","المفتاح"),
    ("بوابة الدخول","صفحة الدخول"),
]
_M={o.lower():n for o,n in _R}
_P=re.compile(
    r'(?<![a-zA-Z؀-ۿ])('+('|'.join(re.escape(o) for o,_ in _R))+
    r')(?![a-zA-Z؀-ۿ])',re.IGNORECASE)
def _r(m):
    w=m.group(0); r=_M.get(w.lower(),w)
    return r.upper() if w.isupper() else (r[0].upper()+r[1:] if w and w[0].isupper() else r)
def sanitize_prompt(t: str) -> str:
    if not t or os.environ.get("WEAVER_PROMPT_SANITIZE","1").lower() in("0","false","off","no"):
        return t
    return _P.sub(_r, t)
