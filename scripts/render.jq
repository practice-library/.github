# Fills one template from policy/constants.json.
#   @@a.b.c@@                 a scalar constant (an error when missing or not a scalar)
#   @@json:a.b@@              any constant, as compact JSON
#   <indent>#@fetch <tool>    fragments/fetch.yml for tools.<tool> (or helpers.<tool>), indented
#   <indent>#@expect <tool>   fragments/expect.yml for tools.<tool>, indented
#   <indent>#@include <file>  fragments/<file>, its own #@ lines expanded the same way, indented. A workflow
#                             includes only the bootstrap it needs before its tooling is checked out
#                             (fragments/self-checkout.yml); everything else runs from that checkout.
#                             A published artifact (spec/ratchet/reconcile.sh) may include its library.
#   #@gen jobs                one job per checks row, and one self-test job per row (self.yml)
#   #@gen with.<check id>     the with: lines for that checks row, every input and optional input from matrix (consumer kit)
#   @@gen:needs@@             the gate's needs: static self jobs, then each check and its self-test
#   @@gen:context@@           the required check name, callerJob / innerJob, after proving both are rendered job ids
#   @@render:<template>@@     that template rendered, as compact JSON for a single-quoted YAML scalar
#   @@gen:unowned@@           one CODEOWNERS line per auto-merge allowlist path, with no owner
#   @@gen:guardids@@          the guard ids, required and optional, comma separated (guard.yml)
#   @@gen:guardidsjson@@      the same ids as a JSON array
# Inputs: $c (constants, --slurpfile), $frags (fragment name -> text), $all (template path -> text), $t (this template).

def lookup($k):
  ($c[0] | getpath($k | split("."))) as $v
  | if $v == null then error("missing constant: " + $k) else $v end;

def scalar($k):
  lookup($k)
  | if (type == "string" or type == "number" or type == "boolean") then tostring
    else error("not a scalar constant: " + $k) end;

def indent($ind): rtrimstr("\n") | split("\n") | map(if . == "" then . else $ind + . end) | join("\n");

def expand:
  gsub("(?<ind>[ ]*)#@(?<f>[a-z]+) (?<t>[A-Za-z0-9_.-]+)";
    . as $m
    | if $m.f == "gen" then $m.ind + "#@gen " + $m.t
      elif $m.f == "include" then ($frags[$m.t] // error("missing fragment: " + $m.t)) | expand | indent($m.ind)
      else ($frags[$m.f + ".yml"] // error("missing fragment: " + $m.f + ".yml"))
        | gsub("@@toolname@@"; $m.t)
        | (if ($c[0].tools // {} | has($m.t)) then "tools." else "helpers." end) as $kind
        | gsub("@@tool\\.(?<k>[A-Za-z0-9_]+)@@"; "@@" + $kind + $m.t + "." + .k + "@@")
        | indent($m.ind)
      end);

def fill:
  gsub("@@json:(?<k>[A-Za-z0-9_.]+)@@"; lookup(.k) | tojson)
  | gsub("@@(?<k>[A-Za-z0-9_.]+)@@"; scalar(.k));

def jobkeys: [scan("(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):[ ]*$") | .[0]];

def withlines($inputs):
  $inputs | map("      " + . + ": ${{ matrix." + . + " }}");

def checkjob($k; $id; $output; $extra):
  ( $extra + withlines($k.inputs + ($k.optionalPathInputs // []) + (($k.optionalInputs // []) - [$extra[] | ltrimstr("      ") | split(":")[0]])) ) as $with
  | [ "  " + $id + ":",
      "    needs: [" + lookup("self.discoverJob") + "]",
      "    strategy:",
      "      fail-fast: false",
      "      matrix:",
      "        include: ${{ fromJSON(needs." + lookup("self.discoverJob") + ".outputs." + $output + "-" + $k.id + ") }}",
      "    uses: ./.github/workflows/" + $k.workflow ]
    + (if ($with | length) > 0 then ["    with:"] + $with else [] end)
  | join("\n");

def checkjobs:
  lookup("checks")
  | map(. as $k
      | checkjob($k; $k.id; "targets"; [])
        + "\n\n"
        + checkjob($k; "selftest-" + $k.id; "fixtures";
            [ "      _selftest-fixture: ${{ matrix.fixture }}",
              "      " + lookup("tools." + $k.tool + ".expectInput") + ": ${{ matrix.expect }}" ]))
  | join("\n\n");

def genwith:
  gsub("(?m)^      #@gen with\\.(?<id>[a-z-]+)$";
    .id as $id
    | ([lookup("checks")[] | select(.id == $id)] | first // error("no checks row: " + $id))
    | withlines(.inputs + (.optionalPathInputs // []) + (.optionalInputs // []))
    | join("\n"));

def genjobs: gsub("(?m)^  #@gen jobs$"; checkjobs) | genwith;

def selfneeds: lookup("self.staticJobs") + (lookup("checks") | map(.id, "selftest-" + .id));

def rendered($path): ($all[$path] // error("missing template: " + $path)) | expand | genjobs | fill;

def context:
  lookup("gate.callerJob") as $caller
  | lookup("gate.innerJob") as $inner
  | if (rendered(lookup("gate.callerWorkflow")) | jobkeys | index([$caller])) == null
      then error("gate.callerJob " + $caller + " is not a job in " + lookup("gate.callerWorkflow"))
    elif (rendered(lookup("gate.workflow")) | jobkeys | index([$inner])) == null
      then error("gate.innerJob " + $inner + " is not a job in " + lookup("gate.workflow"))
    else $caller + " / " + $inner end;

def embed:
  gsub("@@render:(?<p>[A-Za-z0-9_./-]+)@@"; rendered(.p) | fromjson | tojson | gsub("'"; "''"));

def gen:
  gsub("@@gen:(?<k>[a-z]+)@@";
    if .k == "needs" then selfneeds | tojson
    elif .k == "context" then context
    elif .k == "checkids" then lookup("checks") | map(.id) | join(", ")
    elif .k == "guardids" then (lookup("guards.ids") + lookup("guards.optional")) | join(", ")
    elif .k == "guardidsjson" then (lookup("guards.ids") + lookup("guards.optional")) | tojson
    elif .k == "outputs" then
      lookup("checks") | map(.id as $id | ("targets", "fixtures")
        | . + "-" + $id + ": ${{ steps.list.outputs." + . + "-" + $id + " }}") | join("\n      ")
    elif .k == "unowned" then lookup("automerge.allowPaths") | map("/" + .) | join("\n")
    else error("unknown generator: " + .k) end);

def verifyneeds:
  . as $text
  | if ($text | test("@@gen:needs@@")) then
      (rendered(lookup("gate.callerWorkflow")) | jobkeys) as $keys
      | (selfneeds - $keys) as $missing
      | (lookup("gate.mandatoryJobs") - selfneeds) as $unneeded
      | (lookup("guards.ids") - lookup("gate.mandatoryJobs")) as $unguarded
      | if ($missing | length) > 0 then error("gate needs jobs that are not rendered: " + ($missing | tojson))
        elif ($unguarded | length) > 0 then error("guards.ids missing from gate.mandatoryJobs: " + ($unguarded | tojson))
        elif ($unneeded | length) > 0 then error("gate.mandatoryJobs are not among the gate's needs: " + ($unneeded | tojson))
        else $text end
    else $text end;

$t | verifyneeds | expand | genjobs | embed | gen | fill
