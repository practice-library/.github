# Fills one template from policy/constants.json.
#   @@a.b.c@@                 a scalar constant (an error when missing or not a scalar)
#   @@json:a.b@@              any constant, as compact JSON
#   <indent>#@fetch <tool>    fragments/fetch.yml for tools.<tool>, indented
#   <indent>#@expect <tool>   fragments/expect.yml for tools.<tool>, indented
#   <indent>#@include <file>  fragments/<file> as it is, indented
#   #@gen jobs                one job per checks row, and one self-test job per row (self.yml)
#   @@gen:needs@@             the gate's needs: static self jobs, then each check and its self-test
#   @@gen:context@@           the required check name, callerJob / innerJob, after proving both are rendered job ids
#   @@gen:unowned@@           one CODEOWNERS line per auto-merge allowlist path, with no owner
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
      elif $m.f == "include" then ($frags[$m.t] // error("missing fragment: " + $m.t)) | indent($m.ind)
      else ($frags[$m.f + ".yml"] // error("missing fragment: " + $m.f + ".yml"))
        | gsub("@@toolname@@"; $m.t)
        | gsub("@@tool\\.(?<k>[A-Za-z0-9_]+)@@"; "@@tools." + $m.t + "." + .k + "@@")
        | indent($m.ind)
      end);

def fill:
  gsub("@@json:(?<k>[A-Za-z0-9_.]+)@@"; lookup(.k) | tojson)
  | gsub("@@(?<k>[A-Za-z0-9_.]+)@@"; scalar(.k));

def jobkeys: [scan("(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):[ ]*$") | .[0]];

def withlines($inputs):
  $inputs | map("      " + . + ": ${{ matrix." + . + " }}");

def checkjob($k; $id; $output; $extra):
  ( $extra + withlines($k.inputs) ) as $with
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

def genjobs: gsub("(?m)^  #@gen jobs$"; checkjobs);

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

def gen:
  gsub("@@gen:(?<k>[a-z]+)@@";
    if .k == "needs" then selfneeds | tojson
    elif .k == "context" then context
    elif .k == "outputs" then
      lookup("checks") | map(.id as $id | ("targets", "fixtures")
        | . + "-" + $id + ": ${{ steps.list.outputs." + . + "-" + $id + " }}") | join("\n      ")
    elif .k == "unowned" then lookup("automerge.allowPaths") | map("/" + .) | join("\n")
    else error("unknown generator: " + .k) end);

def verifyneeds:
  . as $text
  | if ($text | test("@@gen:needs@@")) then
      ($text | expand | genjobs | fill | jobkeys) as $keys
      | (selfneeds - $keys) as $missing
      | (lookup("gate.requiredJobs") - selfneeds) as $unneeded
      | if ($missing | length) > 0 then error("gate needs jobs that are not rendered: " + ($missing | tojson))
        elif ($unneeded | length) > 0 then error("gate.requiredJobs are not among the gate's needs: " + ($unneeded | tojson))
        else $text end
    else $text end;

$t | verifyneeds | expand | genjobs | gen | fill
