from flask import Flask

app = Flask(__name__)

@app.route("/")
def start():
    return "MBSA's Server Started!!!"
@app.route("/mbsa")
def mbsa():
    return "MBSA's Server Started!!! /mbsa"


if __name__ == '__main__':
    app.run(debug=True, port=5500)