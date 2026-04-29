#!/usr/bin/env bash
# =============================================================================
# docker_cleanup.sh — Комплексная очистка сервера Ubuntu 24.04 + Docker
# =============================================================================
# Использование:
#   chmod +x docker_cleanup.sh
#   sudo ./docker_cleanup.sh            # интерактивный режим
#   sudo ./docker_cleanup.sh --force    # без подтверждений
#   sudo ./docker_cleanup.sh --dry-run  # только показать, ничего не удалять
#   sudo ./docker_cleanup.sh --no-apt   # пропустить очистку APT
# =============================================================================

set -euo pipefail

# ─────────────────────────── Цвета ───────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ─────────────────────────── Параметры ───────────────────────────────────────
FORCE=false
DRY_RUN=false
APT_CLEAN=true
LOG_FILE="/var/log/docker_cleanup_$(date +%Y%m%d_%H%M%S).log"
JOURNALD_VACUUM_SIZE="200M"
JOURNALD_VACUUM_TIME="7d"

for arg in "$@"; do
    case $arg in
        --force)   FORCE=true ;;
        --dry-run) DRY_RUN=true ;;
        --no-apt)  APT_CLEAN=false ;;
    esac
done

# ─────────────────────────── Утилиты ─────────────────────────────────────────
log()  { echo -e "$*" | tee -a "$LOG_FILE"; }
info() { log "${CYAN}[INFO]${NC}  $*"; }
ok()   { log "${GREEN}[OK]${NC}    $*"; }
warn() { log "${YELLOW}[WARN]${NC}  $*"; }
err()  { log "${RED}[ERR]${NC}   $*"; }
head_section() { log "\n${BOLD}${BLUE}═══ $* ═══${NC}"; }

run() {
    if $DRY_RUN; then
        log "${YELLOW}[DRY-RUN]${NC} $*"
    else
        eval "$*" >> "$LOG_FILE" 2>&1 || warn "Команда завершилась с ошибкой: $*"
    fi
}

confirm() {
    $FORCE && return 0
    $DRY_RUN && return 0
    local ans
    read -r -p "$(echo -e "${YELLOW}  → $* [y/N]:${NC} ")" ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

disk_free_kb()    { df / | awk 'NR==2 {print $4}'; }
disk_free_human() { df -h / | awk 'NR==2 {print $4}'; }

# Принимает байты, возвращает человекочитаемую строку
bytes_to_human() {
    local b=${1:-0}
    if (( b < 0 )); then b=0; fi
    if   (( b >= 1073741824 )); then printf "%.1f GB" "$(echo "scale=1; $b/1073741824" | bc)"
    elif (( b >= 1048576    )); then printf "%.1f MB" "$(echo "scale=1; $b/1048576"    | bc)"
    elif (( b >= 1024       )); then printf "%.1f KB" "$(echo "scale=1; $b/1024"       | bc)"
    else printf "%d B" "$b"
    fi
}

# ─────────────────────────── Проверки ────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERR]${NC}   Запустите скрипт с правами root: sudo $0 $*"
    exit 1
fi

if ! command -v docker &>/dev/null; then
    echo -e "${RED}[ERR]${NC}   Docker не найден. Установите Docker и повторите."
    exit 1
fi

if ! docker info &>/dev/null; then
    echo -e "${RED}[ERR]${NC}   Docker daemon не запущен. Запустите: systemctl start docker"
    exit 1
fi

# ─────────────────────────── Старт ───────────────────────────────────────────
clear
log "${BOLD}${BLUE}"
log "╔══════════════════════════════════════════════════════════╗"
log "║        Docker + Ubuntu Server Cleanup Script             ║"
log "║        $(date '+%Y-%m-%d %H:%M:%S')                          ║"
log "╚══════════════════════════════════════════════════════════╝${NC}"
log ""

$DRY_RUN && warn "Режим DRY-RUN: изменений не будет"
info "Лог сохраняется в: $LOG_FILE"

FREE_BEFORE_KB=$(disk_free_kb)
info "Свободно до очистки: $(disk_free_human)"

# ══════════════════════════════════════════════════════════════════════════════
head_section "1. DOCKER — Остановленные контейнеры"
# ══════════════════════════════════════════════════════════════════════════════

STOPPED=$(docker ps -a --filter "status=exited" --filter "status=dead" -q 2>/dev/null | wc -l)
info "Найдено остановленных/мёртвых контейнеров: $STOPPED"

if (( STOPPED > 0 )); then
    docker ps -a --filter "status=exited" --filter "status=dead" \
        --format "  {{.Names}}\t{{.Status}}\t{{.Size}}" 2>/dev/null | column -t || true
    if confirm "Удалить $STOPPED контейнеров?"; then
        run "docker container prune -f"
        ok "Контейнеры удалены"
    fi
else
    ok "Остановленных контейнеров нет"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "2. DOCKER — Образы"
# ══════════════════════════════════════════════════════════════════════════════

DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l)
info "Dangling-образов (без тегов): $DANGLING"

if (( DANGLING > 0 )); then
    if confirm "Удалить $DANGLING dangling-образов?"; then
        run "docker image prune -f"
        ok "Dangling-образы удалены"
    fi
fi

IMAGES_LIST=$(docker images --format "{{.Repository}}:{{.Tag}} {{.Size}}" 2>/dev/null \
    | grep -v "<none>" | head -20 || true)
if [[ -n "$IMAGES_LIST" ]]; then
    info "Текущие образы:"
    echo "$IMAGES_LIST" | awk '{printf "  %-50s %s\n", $1, $2}'
fi

if confirm "Удалить ВСЕ неиспользуемые образы (не задействованные контейнерами)?"; then
    run "docker image prune -a -f"
    ok "Неиспользуемые образы удалены"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "3. DOCKER — Тома (volumes)"
# ══════════════════════════════════════════════════════════════════════════════

VOLS=$(docker volume ls -q --filter "dangling=true" 2>/dev/null | wc -l)
info "Неиспользуемых томов: $VOLS"

if (( VOLS > 0 )); then
    docker volume ls --filter "dangling=true" --format "  {{.Name}}" 2>/dev/null | head -20 || true
    warn "ВНИМАНИЕ: удаление томов необратимо — данные будут потеряны!"
    if confirm "Удалить $VOLS неиспользуемых томов?"; then
        run "docker volume prune -f"
        ok "Тома удалены"
    fi
else
    ok "Неиспользуемых томов нет"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "4. DOCKER — Build cache"
# ══════════════════════════════════════════════════════════════════════════════

# docker system df выводит таблицу; строка "Build Cache" содержит размер в 3-м столбце
CACHE_SIZE=$(docker system df 2>/dev/null \
    | awk '/^Build Cache/ {print $3, $4}' || echo "неизвестно")
info "Размер build cache: $CACHE_SIZE"

if confirm "Очистить build cache?"; then
    run "docker builder prune -a -f"
    ok "Build cache очищен"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "5. DOCKER — Сети"
# ══════════════════════════════════════════════════════════════════════════════

NETS=$(docker network ls --filter "dangling=true" -q 2>/dev/null | wc -l)
info "Неиспользуемых сетей: $NETS"

if (( NETS > 0 )); then
    if confirm "Удалить $NETS неиспользуемых сетей?"; then
        run "docker network prune -f"
        ok "Сети удалены"
    fi
else
    ok "Лишних сетей нет"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "6. DOCKER — Логи контейнеров"
# ══════════════════════════════════════════════════════════════════════════════

info "Анализ логов контейнеров..."
TOTAL_LOG_SIZE=0
BIG_LOGS_COUNT=0
declare -A BIG_LOGS=()

while IFS= read -r cname; do
    [[ -z "$cname" ]] && continue
    LOG_PATH=$(docker inspect --format='{{.LogPath}}' "$cname" 2>/dev/null || true)
    if [[ -n "$LOG_PATH" && -f "$LOG_PATH" ]]; then
        SIZE=$(stat -c%s "$LOG_PATH" 2>/dev/null || echo 0)
        TOTAL_LOG_SIZE=$(( TOTAL_LOG_SIZE + SIZE ))
        if (( SIZE > 10485760 )); then  # > 10 MB
            BIG_LOGS["$cname"]=$SIZE
            BIG_LOGS_COUNT=$(( BIG_LOGS_COUNT + 1 ))
        fi
    fi
done < <(docker ps -a --format '{{.Names}}' 2>/dev/null)

info "Суммарный размер логов контейнеров: $(bytes_to_human "$TOTAL_LOG_SIZE")"

if (( BIG_LOGS_COUNT > 0 )); then
    warn "Контейнеры с большими логами (>10 MB):"
    for cname in "${!BIG_LOGS[@]}"; do
        log "  ${RED}$(bytes_to_human "${BIG_LOGS[$cname]}")${NC}  →  $cname"
    done
    if confirm "Очистить (truncate) логи всех контейнеров?"; then
        while IFS= read -r cname; do
            [[ -z "$cname" ]] && continue
            LOG_PATH=$(docker inspect --format='{{.LogPath}}' "$cname" 2>/dev/null || true)
            if [[ -n "$LOG_PATH" && -f "$LOG_PATH" ]]; then
                run "truncate -s 0 '$LOG_PATH'"
            fi
        done < <(docker ps -a --format '{{.Names}}' 2>/dev/null)
        ok "Логи контейнеров очищены"
    fi
else
    ok "Больших логов контейнеров нет"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "7. СИСТЕМА — Journald (systemd logs)"
# ══════════════════════════════════════════════════════════════════════════════

# journalctl --disk-usage выводит: "Archived and active journals take up X.XG in..."
# grep -oP извлекает число с единицей измерения независимо от локали
JOURNAL_SIZE=$(journalctl --disk-usage 2>/dev/null \
    | grep -oP '[\d.]+ [KMGT]?B' | head -1 || echo "неизвестно")
info "Текущий размер журналов systemd: $JOURNAL_SIZE"

if confirm "Урезать журналы (оставить ≤$JOURNALD_VACUUM_SIZE / ≤$JOURNALD_VACUUM_TIME)?"; then
    run "journalctl --vacuum-size=$JOURNALD_VACUUM_SIZE"
    run "journalctl --vacuum-time=$JOURNALD_VACUUM_TIME"
    ok "Журналы systemd очищены"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "8. СИСТЕМА — APT кэш и мусор"
# ══════════════════════════════════════════════════════════════════════════════

if $APT_CLEAN; then
    APT_CACHE=$(du -sh /var/cache/apt/archives 2>/dev/null | cut -f1 || echo "0")
    info "Размер apt кэша: $APT_CACHE"
    if confirm "Очистить apt кэш и удалить неиспользуемые пакеты?"; then
        run "apt-get autoremove -y"
        run "apt-get autoclean -y"
        run "apt-get clean -y"
        ok "APT кэш очищен"
    fi
else
    info "APT очистка пропущена (--no-apt)"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "9. СИСТЕМА — Старые ядра Linux"
# ══════════════════════════════════════════════════════════════════════════════

CURRENT_KERNEL=$(uname -r)

# mapfile собирает результат в массив — нет проблем с переносами строк
mapfile -t OLD_KERNELS < <(dpkg --list \
    | awk '/^ii.*linux-(image|headers|modules)/ {print $2}' \
    | grep -v "$CURRENT_KERNEL" \
    | grep -v "linux-image-generic" \
    | grep -v "linux-headers-generic" \
    || true)

if (( ${#OLD_KERNELS[@]} > 0 )); then
    warn "Найдено ${#OLD_KERNELS[@]} старых ядер/заголовков:"
    printf "  %s\n" "${OLD_KERNELS[@]}"
    info "Текущее ядро: $CURRENT_KERNEL (не будет удалено)"
    if confirm "Удалить старые ядра?"; then
        # Передаём элементы массива как отдельные аргументы — безопасно
        run "apt-get purge -y ${OLD_KERNELS[*]}"
        run "update-grub"
        ok "Старые ядра удалены"
    fi
else
    ok "Старых ядер нет"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "10. СИСТЕМА — Временные файлы"
# ══════════════════════════════════════════════════════════════════════════════

TMP_SIZE=$(du -sh /tmp 2>/dev/null | cut -f1 || echo "0")
info "Размер /tmp: $TMP_SIZE"

if confirm "Очистить /tmp (файлы старше 1 дня)?"; then
    run "find /tmp -mindepth 1 -maxdepth 1 -mtime +1 -exec rm -rf {} +"
    ok "/tmp очищен"
fi

VAR_TMP_SIZE=$(du -sh /var/tmp 2>/dev/null | cut -f1 || echo "0")
info "Размер /var/tmp: $VAR_TMP_SIZE"

if confirm "Очистить /var/tmp (файлы старше 7 дней)?"; then
    run "find /var/tmp -mindepth 1 -maxdepth 1 -mtime +7 -exec rm -rf {} +"
    ok "/var/tmp очищен"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "11. СИСТЕМА — Старые логи /var/log"
# ══════════════════════════════════════════════════════════════════════════════

LOG_SIZE=$(du -sh /var/log 2>/dev/null | cut -f1 || echo "0")
info "Размер /var/log: $LOG_SIZE"

if confirm "Удалить сжатые старые логи (*.gz, *.1, *.2, *.3) в /var/log?"; then
    run "find /var/log -type f \( -name '*.gz' -o -name '*.1' -o -name '*.2' -o -name '*.3' \) -delete"
    ok "Старые логи удалены"
fi

# ══════════════════════════════════════════════════════════════════════════════
head_section "ИТОГ"
# ══════════════════════════════════════════════════════════════════════════════

FREE_AFTER_KB=$(disk_free_kb)

# Защита от отрицательного значения (место могло не измениться)
FREED_KB=$(( FREE_AFTER_KB - FREE_BEFORE_KB ))
if (( FREED_KB < 0 )); then FREED_KB=0; fi
FREED_BYTES=$(( FREED_KB * 1024 ))

log ""
log "${BOLD}  Свободно до:    $(bytes_to_human $(( FREE_BEFORE_KB * 1024 )))${NC}"
log "${BOLD}  Свободно после: $(bytes_to_human $(( FREE_AFTER_KB  * 1024 )))${NC}"

if $DRY_RUN; then
    warn "  Это был DRY-RUN — реальных изменений нет"
elif (( FREED_BYTES > 0 )); then
    ok "  Освобождено: ~$(bytes_to_human "$FREED_BYTES")"
else
    info "  Изменений в размере не обнаружено (или уже было чисто)"
fi

log ""
info "Подробный лог: $LOG_FILE"