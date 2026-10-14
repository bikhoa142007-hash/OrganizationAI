"""Read-only artifact validation. Never calls the user's application or a model."""
from pathlib import Path
from copy import deepcopy
import json, hashlib, re, sys

ROOT=Path(__file__).resolve().parents[1]
CHECKS=[]
def check(name, ok):
    CHECKS.append({"name":name,"passed":bool(ok)})
def read(rel):
    return json.loads((ROOT/rel).read_text(encoding="utf-8-sig"))
def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def tokens(pointer):
    return [p.replace("~1","/").replace("~0","~") for p in pointer.split("/")[1:]]
def resolve(obj,pointer):
    for token in tokens(pointer):
        obj=obj[int(token)] if isinstance(obj,list) else obj[token]
    return obj
def reverse_patch(current,patch):
    path=patch["path"]
    if path=="":
        return deepcopy(patch.get("before"))
    keys=tokens(path)
    parent=current
    for k in keys[:-1]:
        parent=parent[int(k)] if isinstance(parent,list) else parent[k]
    key=int(keys[-1]) if isinstance(parent,list) else keys[-1]
    if patch["op"]=="add":
        del parent[key]
    elif patch["op"]=="remove":
        if isinstance(parent,list): parent.insert(key,deepcopy(patch["before"]))
        else: parent[key]=deepcopy(patch["before"])
    else:
        parent[key]=deepcopy(patch["before"])
    return current

def validate_fact(inp):
    errors=[]
    try:
        obj=inp["fact_verification"]
        required={"schema_version","verification_status","assertion_origin","issues"}
        if set(obj)!=required: errors.append("invalid fact fields")
        if obj["schema_version"]!="role1.fact-verification/1.0-proposed": errors.append("schema version")
        if obj["assertion_origin"]!="SYNTHETIC_FIXTURE": errors.append("not a synthetic fixture")
        if obj["verification_status"]!="UNCERTAIN" or not obj["issues"]: errors.append("missing unresolved fact")
        evidence={e["evidence_id"]:e for e in inp["agent_outputs"]["vlm"]["evidence"]}
        for issue in obj["issues"]:
            keys={"issue_id","field","affected_input_pointer","issue_type","status","verified_value","sources","evidence_refs","rationale","fixture_rule_ref"}
            if set(issue)!=keys: errors.append("invalid issue fields")
            resolve(inp,issue["affected_input_pointer"])
            if issue["status"]!="UNRESOLVED" or issue["verified_value"] is not None: errors.append("already resolved")
            if len(issue["rationale"])<20 or not issue["evidence_refs"]: errors.append("missing rationale/evidence")
            for eid in issue["evidence_refs"]:
                ev=evidence[eid]
                if issue["issue_id"] not in ev["factual_issue_refs"]: errors.append("issue backlink missing")
                attachment=next(a for a in inp["plan_snapshot"]["attachments"] if a["attachment_id"]==ev["attachment_id"])
                if attachment["sha256"]!=ev["attachment_sha256"]: errors.append("wrong attachment hash")
            normalized=[]
            for source in issue["sources"]:
                required_source={"kind","pointer","observed_value","normalized_value","evidence_ref"}
                if set(source)!=required_source: errors.append("invalid source fields")
                actual=resolve(inp,source["pointer"])
                quote=source["observed_value"]
                if source["kind"]=="PLAN_FIELD":
                    if actual!=quote: errors.append("form value mismatch")
                    if source["evidence_ref"] is not None: errors.append("unexpected form evidence ref")
                elif source["kind"]=="VLM_EVIDENCE":
                    if source["evidence_ref"] not in evidence: errors.append("unknown evidence ID")
                    if not isinstance(actual,str) or not isinstance(quote,str) or quote not in actual: errors.append("quote not in OCR")
                else: errors.append("unknown source kind")
                val=source["normalized_value"]
                if val is not None:
                    if isinstance(quote,(int,float)): parsed=quote
                    else:
                        match=re.search(r"\d[\d.]*",str(quote))
                        parsed=int(match.group().replace(".","")) if match else None
                    if parsed!=val: errors.append("normalized value not supported by quote")
                    normalized.append(val)
            if issue["issue_type"]=="CONFLICTING_VALUES":
                if len(issue["sources"])<2 or len(set(normalized))<2: errors.append("not a genuine conflict")
                if issue["fixture_rule_ref"]!="R1-FIX-CONFLICT-01": errors.append("wrong fixture rule")
            elif issue["issue_type"]=="INCOMPLETE_EXTRACTION":
                ev=evidence[issue["evidence_refs"][0]]
                if ev.get("is_complete") is not False: errors.append("OCR not marked incomplete")
                if ev.get("extraction_mode")!="MOCK_PARTIAL_OCR": errors.append("mock mode missing")
                if "chưa xác minh" not in ev["observed_text"]: errors.append("missing unknown portion")
                if normalized: errors.append("invented known value for incomplete OCR")
                if issue["fixture_rule_ref"]!="R1-FIX-INCOMPLETE-01": errors.append("wrong fixture rule")
            else: errors.append("unsupported issue type")
    except (KeyError,TypeError,ValueError,IndexError,StopIteration) as e:
        errors.append("invalid reference or structure: "+str(e))
    return errors

gt=read("data/ground-truth-cases.json")
vi=read("data/verify-inputs.json")
ve=read("data/verify-expected-results.json")
delta=read("data/changes-v2.1.json")
catalog={"AUTO_APPROVED","HUMAN_REVIEW_REQUIRED"}
check("15 unique GT cases",len(gt)==15 and len({c["id"] for c in gt})==15)
check("5 unique Verify input/expected IDs",len(vi)==len(ve)==5 and {x["id"] for x in vi}=={x["id"] for x in ve})
check("Runtime outcome catalog unchanged",all(c["expected"]["route"] in catalog for c in gt+ve))
check("No app test result forged",all(c["actual"] is None and c["execution_status"]=="NOT_RUN" for c in gt+ve))
check("6/9 GT and 3/2 Verify expected distribution retained",
      sum(c["expected"]["route"]=="AUTO_APPROVED" for c in gt)==6 and
      sum(c["expected"]["route"]=="AUTO_APPROVED" for c in ve)==3)
check("Mock outcome labels match runtime catalog",all(m["expected_route"] in catalog for m in read("data/mock-provider-modes.json")))
base={}
for file_change in delta["files"]:
    current=read(file_change["file"])
    check(file_change["file"]+" current canonical hash",sha(canonical(current))==file_change["after_canonical_sha256"])
    reverted=deepcopy(current)
    for patch in reversed(file_change["patches"]):
        reverted=reverse_patch(reverted,patch)
    check(file_change["file"]+" exact inverse diff to baseline",sha(canonical(reverted))==file_change["before_canonical_sha256"])
    base[file_change["file"]]=reverted

before_gt={c["id"]:c for c in base["data/ground-truth-cases.json"]}
before_vi={c["id"]:c for c in base["data/verify-inputs.json"]}
target={"GT-007","GT-008","GT-009"}
for c in gt:
    inp=c["input"]; old=before_gt[c["id"]]["input"]; name=c["id"]
    check(name+" immutable policy snapshot",inp["policy_snapshot"]==old["policy_snapshot"])
    check(name+" original plan form preserved",inp["plan_snapshot"]==old["plan_snapshot"])
    check(name+" media result/confidence unchanged",inp["agent_outputs"]["media"]==old["agent_outputs"]["media"])
    check(name+" strategy/budget unchanged",inp["agent_outputs"]["strategy"]==old["agent_outputs"]["strategy"] and inp["agent_outputs"]["budget"]==old["agent_outputs"]["budget"])
    check(name+" VLM confidence unchanged",inp["agent_outputs"]["vlm"]["confidence"]==old["agent_outputs"]["vlm"]["confidence"])
    if name not in target:
        check(name+" unrelated input identical",inp==old)
        expected_old=deepcopy(before_gt[name]["expected"])
        if expected_old["route"]=="AUTO_APPROVE": expected_old["route"]="AUTO_APPROVED"
        check(name+" expected unchanged except catalog spelling",c["expected"]==expected_old)
    else:
        errors=validate_fact(inp)
        check(name+" fact evidence and source semantics valid",not errors)
        if errors: print(name,errors,file=sys.stderr)
        check(name+" category/outcome retained",c["expected"]["primary_category"]=="FACT_UNCERTAIN" and c["expected"]["route"]=="HUMAN_REVIEW_REQUIRED")
        check(name+" no final decision",c["expected"]["final_decision"] is None and c["expected"]["decision_source"] is None and c["expected"]["business_status"]=="PENDING_APPROVAL")
        req=c["expected"]["explanation_requirements"]
        issue=inp["fact_verification"]["issues"][0]
        check(name+" explanation tied to actual facts",req["affected_fields"]==[issue["field"]] and req["required_evidence_refs"]==issue["evidence_refs"] and req["required_factual_issue_refs"]==[issue["issue_id"]])
        check(name+" no media-only category oracle","MEDIA_REVIEW_REQUIRED" not in c["expected"]["required_reason_codes"] and req["must_describe_unresolved_fact"])
        check(name+" fixture evaluation hash",inp["evaluation_fixture_hash"]==sha(canonical({k:v for k,v in inp.items() if k!="evaluation_fixture_hash"})))
        check(name+" rationale/policy references present",bool(c["expected"]["rationale"]) and len(c["expected"]["policy_references"])>=3)
    check(name+" plan/policy input hash",inp["input_hash"]==sha(canonical({"plan":inp["plan_snapshot"],"policy":inp["policy_snapshot"]})))

g7=next(c for c in gt if c["id"]=="GT-007")
a4=next(c for c in vi if c["id"]=="VERIFY-A04")
e4=next(c for c in ve if c["id"]=="VERIFY-A04")
normalized=deepcopy(a4["input"])
for ptr in delta["identity_only_differences_allowed_for_A04"]:
    ts=tokens(ptr); parent=normalized
    for token in ts[:-1]: parent=parent[token]
    parent[ts[-1]]=deepcopy(resolve(g7["input"],ptr))
check("VERIFY-A04 full input parity except explicit identity allowlist",normalized==g7["input"])
check("VERIFY-A04 full expected deep equality",e4["expected"]==g7["expected"])
check("VERIFY-A04 fact evidence passes same semantic validation",not validate_fact(a4["input"]))
for v in vi:
    inp=v["input"]
    if v["id"]!="VERIFY-A04": check(v["id"]+" input unchanged",inp==before_vi[v["id"]]["input"])
    check(v["id"]+" input hash",inp["input_hash"]==sha(canonical({"plan":inp["plan_snapshot"],"policy":inp["policy_snapshot"]})))
check("VERIFY-A04 evaluation fixture hash",a4["input"]["evaluation_fixture_hash"]==sha(canonical({k:v for k,v in a4["input"].items() if k!="evaluation_fixture_hash"})))

# Mutations demonstrate that a category label or generic media flag cannot replace evidence.
mutations=[]
x=deepcopy(g7["input"]); del x["fact_verification"]
mutations.append(("Reject media REVIEW_REQUIRED alone as factual proof",x))
x=deepcopy(g7["input"]); x["fact_verification"]["issues"][0]["verified_value"]=50000000
mutations.append(("Reject conflict with an already verified value",x))
x=deepcopy(g7["input"]); x["fact_verification"]["issues"][0]["evidence_refs"]=["NOT-EXISTING"]
mutations.append(("Reject nonexistent evidence reference",x))
x=deepcopy(g7["input"]); x["fact_verification"]["issues"][0]["sources"][1]["observed_value"]="999.000.000 VND"
mutations.append(("Reject unsupported observed quote",x))
x=deepcopy(g7["input"]); x["fact_verification"]["issues"][0]["sources"][1]["normalized_value"]=50000000
mutations.append(("Reject numeric normalization inconsistent with quote",x))
x=deepcopy(g7["input"]); x["fact_verification"]["issues"][0]["sources"]=[deepcopy(x["fact_verification"]["issues"][0]["sources"][0])]*2
mutations.append(("Reject conflict with equal source values",x))
x=deepcopy(next(c for c in gt if c["id"]=="GT-009")["input"]); x["agent_outputs"]["vlm"]["evidence"][0]["is_complete"]=True
mutations.append(("Reject complete OCR labelled as incomplete",x))
x=deepcopy(g7["input"]); x["fact_verification"]["verification_status"]="VERIFIED"
mutations.append(("Reject VERIFIED state with unresolved issues",x))
for name,inp in mutations:
    check(name,bool(validate_fact(inp)))

manifest=read("data/fixture-manifest.json")
for item in manifest["images"]+manifest["files"]:
    p=ROOT/item["path"]
    check(item["path"]+" manifest checksum",p.exists() and sha(p.read_bytes())==item["sha256"])
for source in read("data/source-register.json")["sources"]:
    check(source["snapshot"]+" source bytes preserved",sha((ROOT/source["snapshot"]).read_bytes())==source["sha256"])
mapping=read("data/wp1-wp2-mapping-status.json")
check("WP compatibility not falsely claimed",mapping["status"]=="NOT_VERIFIED" and all(m.get("wp_target_pointer",m.get("wp_output_pointer")) is None for m in mapping["mappings_to_confirm"]))
check("App regression not falsely claimed",mapping["application_regression_execution"]=="NOT_RUN")

broken=[]; invalid=[]; replacement=[]
for p in ROOT.rglob("*.md"):
    text=p.read_text(encoding="utf-8-sig")
    if "\ufffd" in text: replacement.append(str(p.relative_to(ROOT)))
    for link in re.findall(r"\]\(([^)]+)\)",text):
        if link.startswith(("http://","https://","#")): continue
        link=link.split("#")[0]
        if link and not (p.parent/link).exists(): broken.append((str(p.relative_to(ROOT)),link))
    for block in re.findall(r"(?:\x60{3}|~{3})json\s*\n(.*?)(?:\x60{3}|~{3})",text,re.S):
        try: json.loads(block)
        except Exception as ex: invalid.append((str(p.relative_to(ROOT)),str(ex)))
check("Markdown local links resolve",not broken)
check("JSON examples parse",not invalid)
check("Unicode text intact",not replacement)
bad=[c for c in CHECKS if not c["passed"]]
report={
 "artifact_revision":"2.1","validation_scope":"ARTIFACT_ONLY",
 "checks":len(CHECKS),"passed":len(CHECKS)-len(bad),"failed":bad,
 "negative_mutation_controls":len(mutations),
 "category_expectations":{"GT-007":"FACT_UNCERTAIN","GT-008":"FACT_UNCERTAIN","GT-009":"FACT_UNCERTAIN","VERIFY-A04":"FACT_UNCERTAIN"},
 "wp1_wp2_contract_status":"NOT_VERIFIED","engine_regression_status":"NOT_RUN",
 "broken_links":broken,"invalid_json_examples":invalid,
 "check_details":CHECKS
}
print(json.dumps(report,ensure_ascii=False,indent=2))
sys.exit(1 if bad else 0)

