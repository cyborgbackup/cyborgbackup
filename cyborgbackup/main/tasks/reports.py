import datetime
import logging
import os
import smtplib
from email.headerregistry import Address
from email.message import EmailMessage

from django.conf import settings
from jinja2 import FileSystemLoader, Environment

from cyborgbackup.main.models import Job, Catalog
from cyborgbackup.main.models.settings import Setting
from cyborgbackup.main.tasks.helpers import humanbytes

logger = logging.getLogger('cyborgbackup.main.tasks.reports')


def build_report(type):
    since = 24 * 60 * 60
    if type == 'daily':
        since *= 1
    elif type == 'weekly':
        since *= 7
    elif type == 'monthly':
        since *= 31
    started = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=since)
    jobs = Job.objects.filter(started__gte=started, job_type='job')
    total_times = 0
    total_backups = 0
    total_size = 0
    total_deduplicated = 0
    lines = []
    if jobs.exists():
        for job in jobs:
            number_of_files = Catalog.objects.filter(job=job.pk).__len__()
            total_times += job.elapsed
            total_backups += 1
            total_size += job.original_size
            total_deduplicated += job.deduplicated_size
            line = {
                'client': job.client.hostname,
                'type': job.policy.policy_type,
                'status': job.status,
                'duration': str(datetime.timedelta(seconds=float(job.elapsed))),
                'numberFiles': str(number_of_files),
                'original_size': str(humanbytes(job.original_size)),
                'deduplicated_size': str(humanbytes(job.deduplicated_size))
            }
            lines.append(line)
    report = {
        'times': total_times,
        'backups': total_backups,
        'size': humanbytes(total_size),
        'deduplicated': humanbytes(total_deduplicated),
        'lines': lines
    }
    return report


def generate_ascii_table(elements):
    for elt in elements['lines']:
        for col in elements['columns']:
            if len(elt[col['key']]) > col['minsize'] - 2:
                col['minsize'] = len(elt[col['key']]) + 2
    line = '+'
    for col in elements['columns']:
        line += '-' * col['minsize'] + '+'
    header = line + '\n'
    for col in elements['columns']:
        header += '| ' + col['title'].ljust(col['minsize'] - 1)
    header += '|' + '\n' + line
    table = header
    for elt in elements['lines']:
        table += '\n'
        for col in elements['columns']:
            table += '| ' + elt[col['key']].ljust(col['minsize'] - 1)
        table += '|'
    table += '\n' + line
    return table


def generate_html_table(elements):
    table = '<table>\n<thead><tr>'
    for col in elements['columns']:
        table += '<th>' + col['title'] + '</th>\n'
    table += '</tr></thead>\n<tbody>'
    for elt in elements['lines']:
        table += '<tr>'
        for col in elements['columns']:
            table += '<td>' + elt[col['key']] + '</td>\n'
        table += '</tr>\n'
    table += '</tbody></table>\n'
    return table


def generate_html_joboutput(elements):
    output = """Job Output : <div class="job-results-standard-out">
      <div class="JobResultsStdOut">
        <div class="JobResultsStdOut-stdoutContainer">"""
    lineNumber = 1
    for line in elements['lines']:
        output += """<div class="JobResultsStdOut-aLineOfStdOut">
              <div class="JobResultsStdOut-lineNumberColumn">
                <span class="JobResultsStdOut-lineExpander"></span>{}
              </div>
              <div class="JobResultsStdOut-stdoutColumn"><span>{}</span></div>
          </div>""".format(lineNumber, line)
        lineNumber += 1
    output += """</div>
      </div>
    </div>"""
    return output


def send_email(elements, type, mail_to):
    try:
        setting = Setting.objects.get(key='cyborgbackup_mail_from')
        mail_address = setting.value
    except Exception:
        mail_address = 'cyborgbackup@cyborgbackup.local'
    try:
        setting = Setting.objects.get(key='cyborgbackup_mail_server')
        mail_server = setting.value
    except Exception:
        mail_server = 'localhost'
    msg = EmailMessage()
    msg['Subject'] = 'CyBorgBackup Report'
    msg['From'] = Address("CyBorgBackup", mail_address.split('@')[0], mail_address.split('@')[1])
    msg['To'] = mail_to
    if type != 'after':
        ascii_table = generate_ascii_table(elements)
        html_table = generate_html_table(elements)
    else:
        ascii_table = ""
        html_table = generate_html_joboutput(elements)
    logo = os.path.join(settings.BASE_DIR, 'cyborgbackup', 'logo.txt')
    with open(logo) as f:
        logo_text = f.read()
    context = {
        "type": type,
        "logo_text": logo_text,
        "now": datetime.datetime.now(),
        "ascii_table": ascii_table,
        "html_table": html_table
    }
    context.update(elements)
    if type == 'after':
        if elements['state'] == 'successful':
            logo = os.path.join(settings.BASE_DIR, 'cyborgbackup', 'icon_success.txt')
            with open(logo) as f:
                context['state_icon'] = f.read()
            context['state_class'] = "alert-success"
        else:
            logo = os.path.join(settings.BASE_DIR, 'cyborgbackup', 'icon_failed.txt')
            with open(logo) as f:
                context['state_icon'] = f.read()
            context['state_class'] = "alert-failed"

    environment = Environment(loader=FileSystemLoader("templates/"), autoescape=True)
    tmpl_html = environment.get_template("mail_html.j2")
    tmpl_text = environment.get_template("mail_text.j2")

    html_version = tmpl_html.render(context)
    text_version = tmpl_text.render(context)
    msg.set_content(text_version)
    msg.add_alternative(html_version, subtype='html')
    logger.debug('Send Email')
    with smtplib.SMTP(mail_server) as s:
        s.send_message(msg)
