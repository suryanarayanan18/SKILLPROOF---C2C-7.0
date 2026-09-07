import urllib.request
import json
import db

base = 'http://127.0.0.1:8000'

# 1. Create assessment
req = urllib.request.Request(
    f'{base}/api/assessment',
    data=json.dumps({'candidate_id': 'live-demo-user', 'difficulty': 'intermediate'}).encode(),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req) as resp:
    asm = json.loads(resp.read().decode())
print('Assessment created:', asm['id'], '| Problem:', asm['problem']['title'])

# 2. Get reference solution from db
problem_row = db.get_problem(asm['problem']['id'])
ref_sol = problem_row['reference_solution']

# 3. Submit solution
req_submit = urllib.request.Request(
    f'{base}/api/assessment/{asm["id"]}/submit',
    data=json.dumps({'solution': ref_sol, 'time_taken': 32.0}).encode(),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req_submit) as resp:
    result = json.loads(resp.read().decode())
print('Result score:', result['overall_score'], '| Tests passed:', f'{result["tests_passed"]}/{result["tests_total"]}')
print('Stamped versions: Problem', result['problem_version'], '| Calibration', result['calibration_version'], '| Model', result['evaluation_model_version'])

# 4. Test duplicate submission (Must fail with 409)
try:
    with urllib.request.urlopen(req_submit) as resp:
        print('ERROR: Duplicate submission was accepted!')
except urllib.error.HTTPError as e:
    print('Duplicate submission correctly rejected with HTTP', e.code)

# 5. Fetch Skill Passport
with urllib.request.urlopen(f'{base}/api/passport/live-demo-user') as resp:
    passport = json.loads(resp.read().decode())
print('Skill Passport:', passport['passport_id'], '| Overall Score:', passport['overall_score'], '| Verified:', passport['verified'])
print('Competencies:', passport['competencies'])
