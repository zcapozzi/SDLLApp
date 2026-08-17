"""Run schedule generation multiple times to check for non-determinism."""
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.utils.scheduler import ScheduleGenerator, ScheduleViolation

app = create_app()

TIER1_CODES = {'d1', 'slot', 'f1', 'f1c'}
TIER3_CODES = {'e1'}

def run_test(run_num):
    """Generate schedule and return violation counts."""
    with app.app_context():
        generator = ScheduleGenerator(2026, is_spring=0)
        proposal = generator.generate(start_fresh=True)

        violations = proposal.get('violations', [])

        tier1 = [v for v in violations if v['rule_code'] in TIER1_CODES]
        tier3 = [v for v in violations if v['rule_code'] in TIER3_CODES]
        tier2 = [v for v in violations if v['rule_code'] not in TIER1_CODES and v['rule_code'] not in TIER3_CODES]

        return {
            'tier1': len(tier1),
            'tier3': len(tier3),
            'tier2': len(tier2),
            'e1_details': [v['message'] for v in tier3]
        }

print("Running 5 schedule generations to check for non-determinism...\n")

results = []
for i in range(5):
    result = run_test(i + 1)
    results.append(result)
    status = "PASS" if result['tier1'] == 0 and result['tier3'] == 0 else "FAIL"
    print(f"Run {i+1}: Tier I={result['tier1']}, Tier III(e1)={result['tier3']}, Tier II={result['tier2']} - {status}")
    if result['e1_details']:
        for msg in result['e1_details'][:3]:
            print(f"        {msg}")

# Summary
passes = sum(1 for r in results if r['tier1'] == 0 and r['tier3'] == 0)
print(f"\nPassed: {passes}/5")
