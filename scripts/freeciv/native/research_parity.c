/* Native FreeCiv research oracle. Built against the exact pinned source tree.
 *
 * This includes civmanual.c to reuse its complete tool/server linkage stubs. The
 * original main is renamed; all research answers below come from common/research.c.
 */
#define main freeciv_manual_unused_main
#include "civmanual.c"
#undef main

#include "research.h"

static void json_string(FILE *out, const char *value)
{
  const unsigned char *cursor = (const unsigned char *) value;

  fputc('"', out);
  while (*cursor != '\0') {
    switch (*cursor) {
    case '"': fputs("\\\"", out); break;
    case '\\': fputs("\\\\", out); break;
    case '\n': fputs("\\n", out); break;
    case '\r': fputs("\\r", out); break;
    case '\t': fputs("\\t", out); break;
    default:
      if (*cursor < 0x20) {
        fprintf(out, "\\u%04x", (unsigned int) *cursor);
      } else {
        fputc(*cursor, out);
      }
    }
    cursor++;
  }
  fputc('"', out);
}

static void set_known(struct research *presearch, const char *encoded)
{
  char *copy = fc_strdup(encoded);
  char *saveptr = NULL;
  char *name;

  advance_index_iterate(A_FIRST, tech) {
    research_invention_set(presearch, tech, TECH_UNKNOWN);
  } advance_index_iterate_end;
  presearch->techs_researched = 0;

  for (name = strtok_r(copy, "|", &saveptr);
       name != NULL;
       name = strtok_r(NULL, "|", &saveptr)) {
    struct advance *padvance = advance_by_rule_name(name);
    if (padvance == NULL) {
      fprintf(stderr, "unknown input technology: %s\n", name);
      exit(EXIT_FAILURE);
    }
    research_invention_set(presearch, advance_number(padvance), TECH_KNOWN);
    presearch->techs_researched++;
  }
  free(copy);
  research_update(presearch);
}

static void emit_state(const char *state_id, struct research *presearch)
{
  advance_iterate(pgoal) {
    Tech_type_id goal = advance_number(pgoal);
    Tech_type_id step = research_goal_step(presearch, goal);
    bool first = TRUE;

    fputs("{\"goal\":", stdout);
    json_string(stdout, advance_rule_name(pgoal));
    fprintf(stdout, ",\"goal_state\":%d,\"reachable\":%s,\"required\":[",
            research_invention_state(presearch, goal),
            research_invention_reachable(presearch, goal) ? "true" : "false");
    advance_iterate(preq) {
      if (research_goal_tech_req(presearch, goal, advance_number(preq))) {
        if (!first) {
          fputc(',', stdout);
        }
        json_string(stdout, advance_rule_name(preq));
        first = FALSE;
      }
    } advance_iterate_end;
    fputs("],\"state_id\":", stdout);
    json_string(stdout, state_id);
    fputs(",\"step\":", stdout);
    if (valid_advance_by_number(step) == NULL) {
      fputs("null", stdout);
    } else {
      json_string(stdout, advance_rule_name(advance_by_number(step)));
    }
    fprintf(stdout, ",\"unknown_techs\":%d}\n",
            research_goal_unknown_techs(presearch, goal));
  } advance_iterate_end;
  fflush(stdout);
}

int main(int argc, char **argv)
{
  char *line = NULL;
  size_t capacity = 0;
  ssize_t length;
  struct player *pplayer;
  struct research *presearch;

  if (argc != 2) {
    fprintf(stderr, "usage: %s RULESET\n", argv[0]);
    return EXIT_FAILURE;
  }

  fc_interface_init_tool();
  registry_module_init();
  init_character_encodings(FC_DEFAULT_DATA_ENCODING, FALSE);
  srvarg.loglevel = LOG_ERROR;
  init_our_capability();
  init_connections();
  con_log_init(NULL, srvarg.loglevel, srvarg.fatal_assertions);
  i_am_tool();
  game_init(FALSE);
  sz_strlcpy(game.server.rulesetdir, argv[1]);
  settings_init(FALSE);
  game.info.aifill = 0;
  if (!load_rulesets(NULL, NULL, FALSE, NULL, FALSE, FALSE, FALSE)) {
    fprintf(stderr, "failed to load ruleset %s\n", argv[1]);
    return EXIT_FAILURE;
  }

  game.info.team_pooled_research = FALSE;
  pplayer = player_new(player_slot_by_number(0));
  if (pplayer == NULL) {
    fputs("failed to allocate native oracle player\n", stderr);
    return EXIT_FAILURE;
  }
  presearch = research_get(pplayer);

  while ((length = getline(&line, &capacity, stdin)) >= 0) {
    char *tab;
    while (length > 0 && (line[length - 1] == '\n' || line[length - 1] == '\r')) {
      line[--length] = '\0';
    }
    tab = strchr(line, '\t');
    if (tab == NULL) {
      fprintf(stderr, "expected STATE_ID<TAB>TECH|TECH input\n");
      return EXIT_FAILURE;
    }
    *tab = '\0';
    set_known(presearch, tab + 1);
    emit_state(line, presearch);
  }

  free(line);
  con_log_close();
  registry_module_close();
  libfreeciv_free();
  cmdline_option_values_free();
  return EXIT_SUCCESS;
}
