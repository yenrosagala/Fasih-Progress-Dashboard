import os
import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from config import palette_options
from datetime import datetime

def _load_palette():
    import json, os as _os
    cfg_path = "inputs/survey_config.json"
    if _os.path.exists(cfg_path):
        cfg = json.load(open(cfg_path))
        palette_name = cfg.get("palette", "Pastel")
        return palette_options.get(palette_name, palette_options["Pastel"])
    return palette_options["Pastel"]

def get_color(col_name):
    pattern_colors = _load_palette()
    for pattern, color in pattern_colors.items():
        if col_name.upper().startswith(pattern.upper()):
            return color
    return '#C9C9C9'  # fallback for unrecognized statuses


def _get_timestamp_label():
    now = datetime.now()
    day = now.day
    suffix = "th" if 11 <= day <= 13 else {1:"st", 2:"nd", 3:"rd"}.get(day % 10, "th")
    return f"{now.day}{suffix} {now.strftime('%b, %Y')} {now.strftime('%I:%M %p')}"


def _get_survey_display_title(survey_name, title_map):
    return title_map.get(survey_name, survey_name)


def _add_survey_title(ax, survey_name, survey_collection_df, title_map):
    display_title = _get_survey_display_title(survey_name, title_map)
    info = survey_collection_df[survey_collection_df['name'] == survey_name]
    if not info.empty:
        start_val = info['startDate'].values[0] if 'startDate' in info.columns else None
        end_val = info['endDate'].values[0] if 'endDate' in info.columns else None
        parts = []
        if pd.notna(start_val) and pd.notna(end_val):
            start = pd.to_datetime(start_val).strftime('%d %b')
            end = pd.to_datetime(end_val).strftime('%d %b')
            parts.append(f"Pencacahan: {start} – {end}")
        other_jadwal = info['other_jadwal'].values[0] if 'other_jadwal' in info.columns and pd.notna(info['other_jadwal'].values[0]) else ""
        if other_jadwal:
            parts.append(str(other_jadwal))

        ax.set_title(display_title, fontsize=11, pad=14)
        if parts:
            ax.text(
                0.5, 1.02,
                f"[{' | '.join(parts)}]",
                transform=ax.transAxes,
                ha='center', va='bottom',
                fontsize=8
            )
    else:
        ax.set_title(display_title, fontsize=11)


def generate_plots_2(df, survey_collection_df, prefered_status_order, option:int, show_ls=None, filename=None, title_map=None):
    if option not in [1, 2]:
        raise ValueError("Parameter 'option' must be either 1 or 2.")
    os.makedirs("images", exist_ok=True)
    plt.rcParams['font.family'] = ['Roboto Condensed', 'Arial Narrow', 'sans-serif']

    if show_ls is None:
        from survey_selector import load_selected_surveys
        show_ls = load_selected_surveys()

    if title_map is None:
        from survey_selector import load_survey_config
        _config = load_survey_config()
        title_map = {e['name']: e['title'] for e in _config if e.get('title')}

    import json, os as _os
    _cfg_path = "inputs/survey_config.json"
    _top = json.load(open(_cfg_path)) if _os.path.exists(_cfg_path) else {}
    _chart_title = _top.get("chart_title", "Monitoring Statistik Industri")
    _user_title = _top.get("user_assignment_title", "Status Assignment Petugas")

    excluded_cols = {'kd_kab', 'time_stamp', 'name', 'prov_id', 'total', 'assigned', 'have-not-assigned', 'type'}
    if option == 1:
        known = [col for col in prefered_status_order if col in df.columns]
        known_set = set(known)
        extra = [col for col in df.columns if col not in known_set and col not in excluded_cols]
        prefered_status_order = known + extra
    else:
        prefered_status_order = ['assigned', 'have-not-assigned']

    color_map = {col: get_color(col) for col in df.columns if col not in ['kd_kab', 'time_stamp', 'name', 'prov_id', 'total']}

    n = len(show_ls)
    cols = 2
    total_plots = n + 1  # +1 for legend
    rows = math.ceil(total_plots / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(cols * 6, rows * 4))
    axes = axes.flatten()

    for i, survey_name in enumerate(show_ls):
        temp_df = df.loc[
            df['name'] == survey_name,
            ['kd_kab'] + prefered_status_order
        ].copy()

        # Clean numeric columns
        for col in prefered_status_order:
            if pd.api.types.is_numeric_dtype(temp_df[col]):
                temp_df[col] = temp_df[col].fillna(0).astype(int)

        temp_df.set_index('kd_kab', inplace=True)
        temp_df.sort_index(inplace=True)
        x_labels = temp_df.index.tolist()
        x_pos = np.arange(len(x_labels))

        # Adjust bar width dynamically
        if len(x_pos) == 1:
            bar_width = 0.2
        elif len(x_pos) == 2:
            bar_width = 0.15
        else:
            bar_width = 0.5

        bottom = np.zeros(len(x_pos))
        for col in prefered_status_order:
            values = temp_df[col].values

            bars = axes[i].bar(
                x_pos,
                values,
                width=bar_width,
                bottom=bottom,
                label=col,
                color=color_map.get(col, 'black'),
                align='center'
            )

            # Add labels inside each stacked segment
            for j, v in enumerate(values):
                if v > 0:
                    y_center = bottom[j] + v / 2
                    axes[i].text(
                        x_pos[j],
                        y_center,
                        str(v),
                        ha='center',
                        va='center',
                        fontsize=7,
                        color='black'
                    )

            bottom += values

        _add_survey_title(axes[i], survey_name, survey_collection_df, title_map)
    
        axes[i].set_ylabel("Jumlah")

        eps = 1e-6  # small positive constant
        axes[i].set_yscale(
            "function",
            functions=(
                lambda y: np.power(np.clip(y, eps, None), 2/3),
                lambda y: np.power(np.clip(y, eps, None), 3/2)
            )
        )
        
        axes[i].set_xticks(x_pos)
        axes[i].set_xticklabels(x_labels, rotation=45, fontsize=8)
        axes[i].grid(True, axis='y', linestyle='--', alpha=0.5)
        if len(x_pos) == 1:
            axes[i].set_xlim(x_pos[0] - 0.5, x_pos[0] + 0.5)

    # Add legend with section headers if both pencacahan and pemutakhiran are present
    from matplotlib.patches import Patch
    from config import pemutakhiran_status_order as _pem_order

    legend_ax = axes[n]
    legend_ax.axis('off')

    all_legend_labels = [col for col in prefered_status_order if col in color_map]
    pem_set = set(_pem_order)
    pencacahan_labels = [col for col in all_legend_labels if col not in pem_set]
    pemutakhiran_labels = [col for col in all_legend_labels if col in pem_set]
    has_both = bool(pencacahan_labels) and bool(pemutakhiran_labels)

    spacer = Patch(facecolor='none', edgecolor='none')
    handles, labels = [], []

    if has_both:
        handles.append(spacer)
        labels.append('Pencacahan')
    for col in pencacahan_labels:
        handles.append(plt.Rectangle((0, 0), 1, 1, color=color_map[col]))
        labels.append(col)

    if has_both:
        handles.append(spacer)
        labels.append('Pemutakhiran')
    for col in pemutakhiran_labels:
        handles.append(plt.Rectangle((0, 0), 1, 1, color=color_map[col]))
        labels.append(col)

    legend = legend_ax.legend(
        handles=handles,
        labels=labels,
        loc='center',
        fontsize=8,
        frameon=False,
    )
    if has_both:
        for text in legend.get_texts():
            if text.get_text() in ('Pencacahan', 'Pemutakhiran'):
                text.set_fontweight('bold')
                text.set_fontsize(9)

    # Remove extra axes
    for j in range(n + 1, len(axes)):
        fig.delaxes(axes[j])


    timestamp = _get_timestamp_label()

    plt.figtext(
        1, 0.05,
        f"Note *: y-scaled-axis | Last updated: {timestamp}",
        horizontalalignment='right'
    )
    fig.suptitle(_chart_title if option==1 else _user_title, fontsize=18)
    plt.tight_layout(rect=[0, 0.03, 1, 0.98])

    # Save once
    default_name = "images/progress_assignment.png" if option==1 else "images/user_assignment.png"
    plt.savefig(filename or default_name, dpi=600, bbox_inches='tight', pad_inches=0)
    plt.show()


def generate_kabupaten_status_donut_dashboard(
    df,
    survey_collection_df,
    status_order=None,
    show_ls=None,
    filename=None,
    title_map=None,
):
    os.makedirs("images", exist_ok=True)
    plt.rcParams['font.family'] = ['Roboto Condensed', 'Arial Narrow', 'sans-serif']

    if show_ls is None:
        from survey_selector import load_selected_surveys
        show_ls = load_selected_surveys()

    if title_map is None:
        from survey_selector import load_survey_config
        _config = load_survey_config()
        title_map = {e['name']: e['title'] for e in _config if e.get('title')}

    import json, os as _os
    _cfg_path = "inputs/survey_config.json"
    _top = json.load(open(_cfg_path)) if _os.path.exists(_cfg_path) else {}
    _title = _top.get("kabupaten_status_title", "Progres Pencacahan Survei")

    excluded_cols = {'kd_kab', 'time_stamp', 'name', 'prov_id', 'type', 'total'}
    if status_order is None:
        status_order = [col for col in df.columns if col not in excluded_cols]

    n = len(show_ls)
    cols = 2
    total_plots = n + 1  # +1 for legend
    rows = math.ceil(total_plots / cols)

    fig, axes = plt.subplots(rows, cols, figsize=(cols * 6, rows * 4))
    axes = np.array(axes).flatten()

    done_color = get_color("COMPLETED")
    progress_color = get_color("SUBMITTED")
    todo_color = get_color("OPEN")
    empty_color = "#E6E6E6"
    status_labels = []
    status_colors = {}
    legend_counts = {}

    def _status_color(label):
        upper = str(label).upper()
        if upper.startswith("COMPLETED") or upper == "CLEAN":
            return done_color
        if upper.startswith("APPROVED"):
            return get_color("APPROVED")
        if upper.startswith("SUBMITTED"):
            return progress_color
        if upper == "OPEN" or upper == "BELUM_ENTRY":
            return todo_color
        return get_color(label)

    for col in status_order:
        if col not in status_labels and col not in excluded_cols:
            status_labels.append(col)
            status_colors[col] = _status_color(col)

    for i, survey_name in enumerate(show_ls):
        ax = axes[i]
        temp_df = df.loc[df['name'] == survey_name].copy()

        if temp_df.empty:
            counts = pd.Series(dtype=float)
            visible_counts = pd.Series(dtype=float)
            total_respondent = 0.0
            progress_respondent = 0.0
        else:
            value_cols = [col for col in status_labels if col in temp_df.columns]
            for col in value_cols:
                temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce").fillna(0)

            counts = temp_df[value_cols].sum(axis=0) if value_cols else pd.Series(dtype=float)
            total_respondent = float(counts.sum()) if not counts.empty else 0.0
            visible_counts = counts[counts > 0]
            progress_cols = [
                col for col in value_cols
                if str(col).upper().startswith(("APPROVED", "SUBMITTED", "COMPLETED"))
            ]
            progress_respondent = float(temp_df[progress_cols].sum(axis=1).sum()) if progress_cols else 0.0

        sizes = counts.reindex(status_labels, fill_value=0).astype(float).tolist()
        if sum(sizes) == 0:
            sizes = [1]
            colors = [empty_color]
        else:
            colors = [status_colors.get(col, empty_color) for col in status_labels]

        wedges, _ = ax.pie(
            sizes,
            colors=colors,
            startangle=90,
            counterclock=False,
            wedgeprops=dict(width=0.35, edgecolor="white")
        )

        if total_respondent > 0:
            for wedge, value in zip(wedges, sizes):
                if value <= 0:
                    continue
                angle = (wedge.theta2 + wedge.theta1) / 2
                x = 0.78 * np.cos(np.deg2rad(angle))
                y = 0.78 * np.sin(np.deg2rad(angle))
                ax.text(
                    x,
                    y,
                    f"{int(value)}",
                    ha="center",
                    va="center",
                    fontsize=8
                )

        center_pct = (progress_respondent / total_respondent * 100) if total_respondent > 0 else 0.0
        ax.text(0, 0.05, f"{center_pct:.1f}%", ha="center", va="center", fontsize=18, fontweight="bold")
        ax.text(0, -0.15, "approved+submitted+completed", ha="center", va="center", fontsize=8)
        _add_survey_title(ax, survey_name, survey_collection_df, title_map)
        ax.set_aspect("equal")

        for label in visible_counts.index:
            if label not in legend_counts:
                legend_counts[label] = visible_counts[label]

    from matplotlib.patches import Patch
    legend_ax = axes[n]
    legend_ax.axis("off")
    legend_labels = [col for col in status_labels if legend_counts.get(col, 0) > 0]
    handles = [Patch(facecolor=status_colors[col], label=col) for col in legend_labels]
    legend_ax.legend(handles=handles, loc="center", fontsize=9, frameon=False)

    for j in range(n + 1, len(axes)):
        fig.delaxes(axes[j])

    timestamp = _get_timestamp_label()
    plt.figtext(
        1, 0.05,
        f"Note *: slices show total respondent counts by status per survey | Last updated: {timestamp}",
        horizontalalignment='right'
    )
    fig.suptitle(_title, fontsize=18)
    plt.tight_layout(rect=[0, 0.03, 1, 0.98])
    plt.savefig(filename or "images/kabupaten_status.png", dpi=600, bbox_inches='tight', pad_inches=0)
    plt.show()
