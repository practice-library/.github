# Fills one template from policy/constants.json.
#   @@a.b.c@@           a scalar constant (an error when missing or not a scalar)
#   @@json:a.b@@        any constant, as compact JSON
#   <indent>#@<frag> <tool>   the fragment <frag>.yml, indented, with @@tool.X@@ = tools.<tool>.X and @@toolname@@ = <tool>
# Inputs: $c (constants, via --slurpfile), $frags (object name -> text), $t (the template text).

def lookup($k):
  ($c[0] | getpath($k | split("."))) as $v
  | if $v == null then error("missing constant: " + $k) else $v end;

def scalar($k):
  lookup($k)
  | if (type == "string" or type == "number" or type == "boolean") then tostring
    else error("not a scalar constant: " + $k) end;

def expand:
  gsub("(?<ind>[ ]*)#@(?<f>[a-z-]+) (?<t>[A-Za-z0-9_]+)";
    . as $m
    | ($frags[$m.f + ".yml"] // error("missing fragment: " + $m.f))
    | gsub("@@toolname@@"; $m.t)
    | gsub("@@tool\\.(?<k>[A-Za-z0-9_]+)@@"; "@@tools." + $m.t + "." + .k + "@@")
    | rtrimstr("\n") | split("\n")
    | map(if . == "" then . else $m.ind + . end)
    | join("\n"));

def fill:
  gsub("@@json:(?<k>[A-Za-z0-9_.]+)@@"; lookup(.k) | tojson)
  | gsub("@@(?<k>[A-Za-z0-9_.]+)@@"; scalar(.k));

$t | expand | fill
