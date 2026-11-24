"""Optional PyQt editor for one family's articles.

PyQt5 is not imported until the window opens, so the Streamlit app and
ops_svr do not depend on it. Install it with ``pip install 'PyQt5>=5.15.11'``
or ``uv sync --extra qt``.

The table filter and every new or saved row stay on the family id passed
with ``--family-id``.

Features:
- View and edit articles for a specific family
- Add new article records with default values
- Delete selected article records with confirmation
- Save changes to the database
- Refresh data from the database
"""
import argparse
import datetime
import os
import re
import sys

from db_connection import parse_family_id


def article_family_filter(family_id) -> str:
    """SQL filter for one integer family id. Non-numeric values raise."""
    number = parse_family_id(family_id)
    if number is None:
        raise ValueError("family_id is required")
    return f"family_id = {number}"


def build_parser():
    parser = argparse.ArgumentParser(description="Article batch editor for one family")
    parser.add_argument("--db", type=str, help="Path to the SQLite database")
    parser.add_argument("--table", type=str, help="Article table name")
    parser.add_argument(
        "--family-id",
        "--family_id",
        dest="family_id",
        required=True,
        help="Integer family whose articles this window may edit",
    )
    return parser


def _import_qt():
    from PyQt5.QtCore import QDateTime
    from PyQt5.QtSql import QSqlDatabase, QSqlQuery, QSqlTableModel
    from PyQt5.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QTableView,
        QVBoxLayout,
        QWidget,
    )
    return {
        "QDateTime": QDateTime,
        "QSqlDatabase": QSqlDatabase,
        "QSqlQuery": QSqlQuery,
        "QSqlTableModel": QSqlTableModel,
        "QApplication": QApplication,
        "QHBoxLayout": QHBoxLayout,
        "QMainWindow": QMainWindow,
        "QMessageBox": QMessageBox,
        "QPushButton": QPushButton,
        "QTableView": QTableView,
        "QVBoxLayout": QVBoxLayout,
        "QWidget": QWidget,
    }


def show_window(db_path, table_name, family_id):
    """Open the editor. family_id must be an integer."""
    number = parse_family_id(family_id)
    if number is None:
        raise SystemExit("ops_artBatch requires a numeric --family-id")
    qt = _import_qt()
    QApplication = qt["QApplication"]
    QDateTime = qt["QDateTime"]
    QHBoxLayout = qt["QHBoxLayout"]
    QMainWindow = qt["QMainWindow"]
    QMessageBox = qt["QMessageBox"]
    QPushButton = qt["QPushButton"]
    QSqlDatabase = qt["QSqlDatabase"]
    QSqlQuery = qt["QSqlQuery"]
    QSqlTableModel = qt["QSqlTableModel"]
    QTableView = qt["QTableView"]
    QVBoxLayout = qt["QVBoxLayout"]
    QWidget = qt["QWidget"]
    family_filter = article_family_filter(number)

    class DatabaseViewer(QMainWindow):
        def __init__(self, database_path, table, family):
            super().__init__()
            self.family_id = family
            self.table_name = table
            self.setWindowTitle(f"Articles for family_id {family}")
            self.setGeometry(100, 100, 1100, 640)
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            buttons = QHBoxLayout()
            self.save_button = QPushButton("Save Changes")
            self.save_button.clicked.connect(self.save_changes)
            self.save_button.setEnabled(False)
            add_button = QPushButton("Add Record")
            add_button.clicked.connect(self.insert_record)
            delete_button = QPushButton("Delete")
            delete_button.clicked.connect(self.delete_record)
            refresh_button = QPushButton("Refresh")
            refresh_button.clicked.connect(self.refresh_data)
            buttons.addWidget(self.save_button)
            buttons.addWidget(add_button)
            buttons.addWidget(delete_button)
            buttons.addWidget(refresh_button)
            buttons.addStretch()
            layout.addLayout(buttons)
            if not self._init_database(database_path, table):
                return
            self.tableView = QTableView()
            self.tableView.setEditTriggers(QTableView.DoubleClicked | QTableView.EditKeyPressed)
            self.tableView.setSelectionBehavior(QTableView.SelectRows)
            layout.addWidget(self.tableView)
            self.tableView.setModel(self.model)
            self.model.select()
            self.model.dataChanged.connect(self.on_data_changed)
            self.tableView.resizeColumnsToContents()

        def _init_database(self, database_path, table):
            self.db = QSqlDatabase.addDatabase("QSQLITE")
            self.db.setDatabaseName(database_path)
            folder = os.path.dirname(database_path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            if not self.db.open():
                QMessageBox.critical(self, "Database Error", self.db.lastError().text())
                return False
            if table not in self.db.tables():
                QMessageBox.critical(
                    self,
                    "Table Error",
                    f"{table} is missing. Start the app once so init_db() creates it.",
                )
                return False
            self.model = QSqlTableModel(self, self.db)
            self.model.setTable(table)
            self.model.setEditStrategy(QSqlTableModel.OnManualSubmit)
            self.model.setFilter(family_filter)
            if not self.model.select():
                QMessageBox.critical(self, "Error", self.model.lastError().text())
                return False
            return True

        def on_data_changed(self, top_left, _bottom_right, _roles=None):
            if top_left.column() == self.model.fieldIndex("updated_at"):
                return
            self.save_button.setEnabled(True)
            current = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
            self.model.blockSignals(True)
            self.model.setData(self.model.index(top_left.row(), self.model.fieldIndex("updated_at")), current)
            self._pin_family(top_left.row())
            self.model.blockSignals(False)

        def _pin_family(self, row):
            column = self.model.fieldIndex("family_id")
            if column < 0:
                return
            self.model.setData(self.model.index(row, column), self.family_id)

        def insert_record(self):
            row = self.model.rowCount()
            if not self.model.insertRow(row):
                QMessageBox.critical(self, "Error", self.model.lastError().text())
                return
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            defaults = {
                "title": "New Article",
                "content": "",
                "category": "News",
                "author": "",
                "source": "",
                "src_url": "",
                "image_url": "",
                "l10n": "US",
                "created_at": now,
                "updated_at": now,
                "is_censored": 0,
                "user_id": 0,
                "family_id": self.family_id,
            }
            for field, value in defaults.items():
                column = self.model.fieldIndex(field)
                if column < 0:
                    continue
                self.model.setData(self.model.index(row, column), value)
            self.tableView.scrollToBottom()
            title_column = self.model.fieldIndex("title")
            self.tableView.setCurrentIndex(self.model.index(row, title_column))
            self.tableView.edit(self.model.index(row, title_column))
            self.save_button.setEnabled(True)

        def delete_record(self):
            selected = self.tableView.selectionModel().selectedRows()
            if not selected:
                QMessageBox.information(self, "No Selection", "Please select a row to delete.")
                return
            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete {len(selected)} selected row(s)?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                for index in sorted(selected, reverse=True):
                    self.model.removeRow(index.row())
                self.save_button.setEnabled(True)

        def save_changes(self):
            if not self.model.isDirty():
                return
            for row in range(self.model.rowCount()):
                self._pin_family(row)
            if not self.db.transaction():
                QMessageBox.critical(self, "Database Error", self.db.lastError().text())
                return
            try:
                if not self.model.submitAll():
                    raise RuntimeError(self.model.lastError().text())
                if not self.db.commit():
                    raise RuntimeError(self.db.lastError().text())
                self.model.setFilter(family_filter)
                self.model.select()
                self.save_button.setEnabled(False)
                self._verify_count()
            except Exception as exc:
                if self.db.isOpen():
                    self.db.rollback()
                self.model.revertAll()
                self.model.select()
                QMessageBox.critical(self, "Save Error", str(exc))
                self.save_button.setEnabled(True)

        def _verify_count(self):
            query = QSqlQuery(self.db)
            if query.exec_(f"SELECT COUNT(*) FROM {self.table_name} WHERE {family_filter}") and query.next():
                if query.value(0) != self.model.rowCount():
                    print(
                        f"Warning: family {self.family_id} has {query.value(0)} rows "
                        f"in the database and {self.model.rowCount()} in the editor"
                    )
            query.finish()

        def refresh_data(self):
            self.model.setFilter(family_filter)
            self.model.select()
            self.tableView.resizeColumnsToContents()
            self.save_button.setEnabled(False)

    app = QApplication.instance() or QApplication(sys.argv)
    window = DatabaseViewer(db_path, table_name, number)
    window.show()
    sys.exit(app.exec_())


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        family_id = parse_family_id(args.family_id)
    except ValueError as exc:
        raise SystemExit(f"ops_artBatch requires a numeric family id. {exc}") from exc
    if family_id is None:
        raise SystemExit("ops_artBatch requires a numeric --family-id")
    import db_utils as dbm
    table_name = args.table or dbm.db_tables["articles"]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise SystemExit(f"Invalid table name: {table_name!r}")
    db_path = args.db or dbm.db_path
    table = table_name
    previous = dbm.database_name
    dbm.database_name = db_path
    try:
        dbm.init_db()
    finally:
        dbm.database_name = previous
    show_window(db_path, table, family_id)


if __name__ == "__main__":
    main()
