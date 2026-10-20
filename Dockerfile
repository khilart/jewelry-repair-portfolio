FROM odoo:17
USER root
RUN pip3 install --no-cache-dir trimesh xlsxwriter xlrd anthropic
USER odoo
