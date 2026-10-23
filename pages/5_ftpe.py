# Modules required
import os
import pandas as pd  # pip install pandas
import datetime
import time  # 添加 time 模組導入
from dotenv import load_dotenv  # pip install python-dotenv
from pathlib import Path  # 添加這行導入

# Import Web App modules
import streamlit as st  # pip install streamlit

# Import graphviz module
import graphviz as gv  # pip install graphviz

# Import utility functions
import funcUtils as fu
import context_utils as cu
import db_utils as dbm

# Import performance logging modules
import logging
from glogTime import func_timer_decorator


# --- Initialize system environment --- from here
script_path = Path(__file__).resolve()
script_dir = script_path.parent
env_path = script_dir / '.env'

# 載入 .env 文件
load_dotenv(env_path, override=True)

# --- Set Server logging levels ---
g_logging = os.getenv("LOGGING", "INFO").strip('\"\'').upper()  # 預設為 INFO，並移除可能的引號

# 創建日誌器
logger = logging.getLogger(__name__)

# 設置日誌格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

# 設置控制台處理器
console_handler = logging.StreamHandler()

# 根據環境變數設置日誌級別
if g_logging == "DEBUG":
    logger.setLevel(logging.DEBUG)
    console_handler.setLevel(logging.DEBUG)
    logger.debug("Debug logging is enabled")
else:
    logger.setLevel(logging.INFO)
    console_handler.setLevel(logging.INFO)

console_handler.setFormatter(formatter)

# 移除所有現有的處理器，避免重複日誌
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 添加處理器到日誌器
logger.addHandler(console_handler)

# 確保根日誌器不會干擾
logging.basicConfig(level=logging.WARNING)
logging.getLogger().setLevel(logging.WARNING)

# 打印所有環境變數用於調試
logger.debug("Environment variables:")
for key, value in os.environ.items():
    if key == 'LOGGING' or key.startswith('L10N') or key.startswith('DIRTY'):
        logger.debug(f"{key}={value}")

# --- Internal Functions --- from here
def build_spouse_graph(dbuff):
    """
    建立家庭樹圖形，從成員指向其配偶開始，
    然後再由女性配偶指向其子女（如果有的話）。

    Args:
        dbuff (dict): 包含成員記錄的字典，包含以下鍵值：
            - Name: 成員姓名
            - Born: 出生年
            - Order: 代數順序
            - Died: 死亡年
            - Href: 相關連結
            - Status: 婚姻狀態
            - Spouse: 配偶資訊

    Returns:
        graphviz.Digraph: 包含家庭關係的圖形物件

    Raises:
        FileNotFoundError: 當成員記錄不存在時
    """
    logger.debug(f"Entering build_spouse_graph with dbuff: {dbuff}")
    
    try:
        global g_loc
        global g_single, all_members

        mem = dbuff["Name"]
        born = dbuff["Born"]
        order = dbuff["Order"]

        filter = "Name == @mem and Born == @born and Order == @order"
        rec = all_members.query(filter)
        if rec.empty:
            logger.error(f"Member not found: {mem}, {born}, {order}")
            raise FileNotFoundError(f"Member not found: {mem}, {born}, {order}")

        logger.debug(f"Found Member: {rec}")
        # Create a graph object with graphviz
        dot = gv.Digraph(name=mem, comment=f"{mem} G{order} Graph", engine="twopi")

        # set graph attributes
        dot.attr("graph", overlap="scalexy", layout="twopi")
        dot.attr("node", shape="circle")

        # Add member node
        mem_label = f"{mem}\n{born}-{dbuff['Died']}"
        if dbuff["Href"].startswith("http"):
            dot.node(
                mem, 
                label=mem_label, 
                shape="doubleoctagon", 
                style="filled", 
                href=dbuff["Href"]
            )
        else:
            dot.node(
                mem, 
                label=mem_label, 
                shape="doubleoctagon", 
                style="filled"
            )

        # check if this male-member not married
        if rec.Status.iloc[0] == g_single:
            # single
            return dot

        # iterating this male-member list of spouses
        cnt_sp = len(rec.Spouse.index)
        for i, w in zip(range(cnt_sp), rec.Spouse):
            married = rec.Married.iloc[i]
            filter = "Name == @w and Spouse == @mem"
            rec_sp = all_members.query(filter)
            if rec_sp.empty:
                # spouse info is not on file
                spouse_label = (
                    f"{w}\n{g_loc['MEMBER_NOT_REG']}\n{g_loc['MARRIED_IN']}{married}"
                )
                href = ""
            else:
                # spouse info exists
                logger.debug(f"Found Spouses: {rec_sp}")

                born = rec_sp.Born.iloc[0]
                died = rec_sp.Died.iloc[0]
                spouse_label = f"{w}\n{born}-{died}\n{g_loc['MARRIED_IN']}{married}"
                href = rec_sp.Href.iloc[0]
            if href.startswith("http"):
                dot.node(
                    w, 
                    label=spouse_label, 
                    color="aquamarine", 
                    style="filled",
                    href=href
                )
            else:
                dot.node(
                    w, 
                    label=spouse_label, 
                    color="aquamarine", 
                    style="filled"
                )

            # Add edges from Dad to Mom
            dot.attr("edge", color="red")
            dot.edge(dbuff["Name"], w, label=g_loc["REL_MARRIED"])

            # search for any kids, whose Mom is 'w'
            filter = "Mom == @w"
            all_members['Name'] = all_members['Name'].astype(str)
            all_members['Dad'] = all_members['Dad'].astype(str)
            all_members['Mom'] = all_members['Mom'].astype(str)
            kids = all_members.query(filter)
            if kids.empty:
                # no kids associated with this Mom
                continue  # to the next spouse

            # found kids
            # drop duplicated rows with the same name, and birth-year
            kids = kids.drop_duplicates(subset=["Name", "Born"], keep="first")

            logger.debug(f"Found Kids: {kids}")
            # add nodes for kids, associated with this Mom
            with dot.subgraph(name=f'cluster_{w}') as s:
                logger.debug(f"Subgraph for kids: {s}")
                s.attr("graph", label=w, rank="same")

                # loop thru the list of kids
                for k in kids.Name:
                    # Filter 用法錯誤，不能直接使用 @dbuff["Name"]
                    dbuff["Name"]
                    filter = "Name == @k and Dad == @d_name and Mom == @w"
                    logger.debug(f"Search for right kid: {filter}")
                    rec_k = all_members.query(filter)
                    logger.debug(f"Search for right kid: {rec_k}")
                    if rec_k.empty:
                        # kid's info not on file
                        href = ""
                        logger.debug(f"Kid not found: {k}, continue")
                        continue  # to the next kid
                    else:
                        # kid's info found
                        born = int(rec_k.Born.iloc[0]) if pd.notna(rec_k.Born.iloc[0]) else 0
                        died = int(rec_k.Died.iloc[0]) if pd.notna(rec_k.Died.iloc[0]) else 0
                        rel = int(rec_k.Relation.iloc[0]) if pd.notna(rec_k.Relation.iloc[0]) else 0
                        kid_label = f"{k}\n{born}-{died}"
                        href = rec_k.Href.iloc[0] if pd.notna(rec_k.Href.iloc[0]) else ""
                        logger.debug(f"Found Kid: {k}, {born}, {died}, {rel}, {href}")

                        # add kid node
                        if href.startswith("http"):
                            s.node(k, label=kid_label, shape="box", href=href)
                        else:
                            s.node(k, label=kid_label, shape="box")

                        # Add directed edge from Mom to kid
                        if g_lrelation[rel] == g_loc["REL_ADOPT"]:
                            dot.attr("edge", color="green")
                            dot.edge(w, k, label=g_loc["REL_ADOPT"])
                        elif g_lrelation[rel] == g_loc["REL_STEP"]:
                            dot.attr("edge", color="blue")
                            dot.edge(w, k, label=g_loc["REL_STEP"])
                        else:
                            dot.attr("edge", color="black")
                            dot.edge(w, k, label=g_loc["REL_BIO"])

                        # check if kid not married
                        if rec_k.Status.iloc[0] == g_single:
                            # single
                            logger.debug(f"Kid single: {k}, continue")    
                            continue  # to the next kid

                        # This kid not single, iterating married kid's spouse list
                        cnt_kw = len(rec_k.Spouse.index)
                        for i, kw in zip(range(cnt_kw), rec_k.Spouse):
                            # find out marriage-year
                            married = rec_k.Married.iloc[i] if pd.notna(rec_k.Married.iloc[i]) else 0

                            # search for kid's spouse
                            filter = "Name == @kw and Spouse == @k"
                            logger.debug(f"Search for kid's spouse: {filter}")
                            rec_kw = all_members.query(filter)
                            if rec_kw.empty:
                                # kid's spouse info not registered, skip
                                logger.debug(f"Kid's spouse not found: {k}, {kw}, continue")
                                continue
                            else:
                                born = int(rec_kw.Born.iloc[0]) if pd.notna(rec_kw.Born.iloc[0]) else 0
                                died = int(rec_kw.Died.iloc[0]) if pd.notna(rec_kw.Died.iloc[0]) else 0
                                spouse_label = (
                                    f"{kw}\n{born}-{died}\n{g_loc['MARRIED_IN']}{married}"
                                )
                                href = rec_kw.Href.iloc[0] if pd.notna(rec_kw.Href.iloc[0]) else ""
                                logger.debug(f"Found Kid's Spouse: {kw}, {born}, {died}, {spouse_label}, {href}")

                            # Add kid's spouse node
                            if href.startswith("http"):
                                dot.node(
                                    kw,
                                    label=spouse_label,
                                    color="lightblue",
                                    style="filled",
                                    href=href,
                                )
                            else:
                                dot.node(
                                    kw, 
                                    label=spouse_label, 
                                    color="lightblue", 
                                    style="filled"
                                )
                            # join the subgraph
                            s.node(kw)

                            # Add directed edge from kid to kw
                            dot.attr("edge", color="red")
                            dot.edge(k, kw, label=g_loc["REL_MARRIED"])
    except FileNotFoundError as e:
        logger.error(f"File not found error in build_spouse_graph: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in build_spouse_graph: {e}")
        raise
    logger.debug(f"build_spouse_graph: {dot} returned")
    return dot


# Display the basic info about member's Dad(s) via Streamlit
def display_dad(dmem):
    """
    透過Streamlit顯示成員父親的基本資訊

    Args:
        dmem (dict): 包含成員資訊的字典

    Returns:
        None
    """
    global all_members, bio_members, adopt_members, step_members
    global g_loc, g_lrelation

    mem = dmem["Name"]
    born = dmem["Born"]
    dad_name = dmem["Dad"]
    rel = dmem["Relation"]
    if dad_name == "?":
        # Dad's info not registered
        desc = f"#### => {g_loc['DAD']}({g_loc['REL_BIO']}): {dad_name} {g_loc['MEMBER_NOT_REG']}"
        st.markdown(desc)
        return

    # retrieve bio-Dad info
    if rel == g_lrelation.index(g_loc["REL_BIO"]):
        bio_dad_name = dad_name
    else:
        # locate bio-Dad's name
        filter = "Name == @mem"
        dads = bio_members.query(filter)
        if dads.empty:
            # Member's info not registered
            desc = f"#### => {g_loc['DAD']}({g_loc['REL_BIO']}): {mem} {g_loc['MEMBER_NOT_REG']}"
            st.markdown(desc)
            return
        else:
            bio_dad_name = dads.Dad.iloc[0]

    filter = "Name == @bio_dad_name"
    dads = all_members.query(filter)
    if dads.empty:
        # Dad's info not registered
        desc = f"#### => {g_loc['DAD']}({g_loc['REL_BIO']}): {bio_dad_name} {g_loc['MEMBER_NOT_REG']}"
    else:
        # bio-Dad's info found
        born = dads.Born.iloc[0]
        died = dads.Died.iloc[0]
        dad_label = f"{bio_dad_name} {born}-{died}"
        dad_href = dads.Href.iloc[0]
        desc = f"#### => {g_loc['DAD']}({g_loc['REL_BIO']}): [{dad_label}]({dad_href})"
    st.markdown(desc)

    # setup filter for extra Dads?
    filter = "Name == @mem"
    filter_dad = "Dad == @mem"

    # any adopted-Dads?
    if not adopt_members.empty:
        dads = adopt_members.query(filter)
        if not dads.empty:
            # display adopted-Dads
            # need to iterate dataframe
            for idx in dads.index:
                name = dads["Dad"][idx]
                st.markdown(f"#### => {g_loc['DAD']}({g_loc['REL_ADOPT']}): {name}")

    # any adopted-Kids?
    if not adopt_members.empty:
        kids = adopt_members.query(filter_dad)
        if not kids.empty:
            # display adopted-kids
            # need to iterate dataframe
            for idx in kids.index:
                name = kids["Name"][idx]
                st.markdown(f"#### => {g_loc['KID']}({g_loc['REL_ADOPT']}): {name}")

    # any step-Dads?
    if not step_members.empty:
        dads = step_members.query(filter)
        if not dads.empty:
            # display step-Dads
            # need to iterate dataframe
            for idx in dads.index:
                name = dads["Dad"][idx]
                st.markdown(f"#### => {g_loc['DAD']}({g_loc['REL_STEP']}): {name}")

    # any step-Kids?
    if not step_members.empty:
        kids = step_members.query(filter_dad)
        if not kids.empty:
            # display step-kids
            # need to iterate dataframe
            for idx in kids.index:
                name = kids["Name"][idx]
                st.markdown(f"#### => {g_loc['KID']}({g_loc['REL_STEP']}): {name}")

    return


# Display the basic info about member's Mom(s) via Streamlit
def display_mom(dmem):
    """
    透過Streamlit顯示成員母親的基本資訊

    Args:
        dmem (dict): 包含成員資訊的字典

    Returns:
        None
    """
    global all_members, bio_members, adopt_members, step_members
    global g_loc, g_lrelation

    mem = dmem["Name"]
    born = dmem["Born"]
    mom_name = dmem["Mom"]
    rel = dmem["Relation"]

    # Member's info not registered
    if mom_name == "?":
        # Mom's info not registered
        desc = f"#### => {g_loc['MOM']}({g_loc['REL_BIO']}): {mom_name} {g_loc['MEMBER_NOT_REG']}"
        st.markdown(desc)
        return

    # Retrieve bio-Mom info
    # retrieve bio-Mom info
    if rel == g_lrelation.index(g_loc["REL_BIO"]):
        bio_mom_name = mom_name
    else:
        # Locate bio-Mom's name
        # locate bio-Mom's name
        filter = "Name == @mem"
        moms = bio_members.query(filter)
        if moms.empty:
            # Member's info not registered
            desc = f"#### => {g_loc['MOM']}({g_loc['REL_BIO']}): {mem} {g_loc['MEMBER_NOT_REG']}"
            st.markdown(desc)
            return
        else:
            bio_mom_name = moms.Mom.iloc[0]

    # Get the basic info of bio-Mom
    filter = "Name == @bio_mom_name"
    moms = all_members.query(filter)
    if moms.empty:
        # Mom's info not registered
        desc = f"#### => {g_loc['MOM']}({g_loc['REL_BIO']}): {bio_mom_name} {g_loc['MEMBER_NOT_REG']}"
    else:
        # Bio-Mom's info found
        # bio-Mom's info found
        born = moms.Born.iloc[0]
        died = moms.Died.iloc[0]
        mom_label = f"{bio_mom_name} {born}-{died}"
        mom_href = moms.Href.iloc[0]
        desc = f"#### => {g_loc['MOM']}({g_loc['REL_BIO']}): [{mom_label}]({mom_href})"
    st.markdown(desc)
    display_kids(bio_mom_name)

    # setup filter for extra Moms
    filter = "Name == @mem"
    filter_mom = "Mom == @mem"

    # Any adopted-Moms?
    # any adopted-Moms?
    if not adopt_members.empty:
        moms = adopt_members.query(filter)
        if not moms.empty:
            # Display adopted-Moms
            # Need to iterate dataframe
            # display adopted-Moms
            # need to iterate dataframe
            for idx in moms.index:
                name = moms["Mom"][idx]
                st.markdown(f"#### => {g_loc['MOM']}({g_loc['REL_ADOPT']}): {name}")

    # Any adopted-Kids?
            # mom_name = moms.Mom.iloc[0]
            # # check if adopted-Mom is bio-Mom or not
            # if mom_name != bio_mom_name:
            #     # display adopted-Mom
            #     st.markdown(f"#### => {g_loc['MOM']}({g_loc['REL_ADOPT']}): {mom_name}")

    # any adopted-Kids?
    if not adopt_members.empty:
        kids = adopt_members.query(filter_mom)
        if not kids.empty:
            # Display adopted-kids
            # Need to iterate dataframe
            # display adopted-kids
            # need to iterate dataframe
            for idx in kids.index:
                name = kids["Name"][idx]
                st.markdown(f"#### => {g_loc['KID']}({g_loc['REL_ADOPT']}): {name}")

    # Any step-Moms?
    if not step_members.empty:
        moms = step_members.query(filter)
        if not moms.empty:
            # display step-Moms
            for idx in moms.index:
                name = moms["Mom"][idx]
                st.markdown(f"#### => {g_loc['MOM']}({g_loc['REL_STEP']}): {name}")

    # Any step-Kids?
            # mom_name = moms.Mom.iloc[0]
            # # check if adopted-Mom is bio-Mom or not
            # if mom_name != bio_mom_name:
            #     # display step-Mom
            #     st.markdown(f"#### => {g_loc['MOM']}({g_loc['REL_STEP']}): {mom_name}")

    # any step-Kids?
    if not step_members.empty:
        kids = step_members.query(filter_mom)
        if not kids.empty:
            # Display step-kids
            # Need to iterate dataframe
            # display step-kids
            # need to iterate dataframe
            for idx in kids.index:
                name = kids["Name"][idx]
                st.markdown(f"#### => {g_loc['KID']}({g_loc['REL_STEP']}): {name}")

    return


# Display the basic info about member's Spouse via Streamlit
def display_spouse(dmem):
    """
    透過Streamlit顯示成員配偶的基本資訊

    Args:
        dmem (dict): 包含成員資訊的字典

    Returns:
        None
    """
    global all_members
    global g_loc

    dmem["Name"]
    born = dmem["Born"]
    sp_name = dmem["Spouse"]
    married = dmem["Married"]

    # skip if member is still single
    if dmem["Status"] == g_single:
        # member is single, no Spouse found
        return

    # member not single, find the list of Spouses
    # get the basic info of spouse
    filter = "Name == @sp_name and Spouse == @mem"
    rec_sp = all_members.query(filter)
    if rec_sp.empty:
        # spouse info not found
        desc = f"#### => {g_loc['SPOUSE']}: {sp_name} {g_loc['MEMBER_NOT_REG']}"
        st.markdown(desc)
    else:
        # Spouse info exists
        born = rec_sp.Born.iloc[0]
        died = rec_sp.Died.iloc[0]
        spouse_label = f"{sp_name} {born}-{died}"
        spouse_href = rec_sp.Href.iloc[0]
        desc = f"#### => {g_loc['SPOUSE']}：[{spouse_label}]({spouse_href})"

        # display kids if female
        sp_sex = g_lsex[rec_sp.Sex.iloc[0]]
        if sp_sex != g_loc["SEX_MALE"] and sp_sex != g_loc["SEX_INLAW_MALE"]:
            married = rec_sp.Married.iloc[0]
            desc = desc + f", {g_loc['MARRIED_IN']}{married}"
            st.markdown(desc)
            display_kids(sp_name)
        else:
            st.markdown(desc)
    return


# Display the basic info about kids who are bilogically
# related to Mom via Streamlit.
def display_kids(w):
    """
    透過Streamlit顯示與母親有血緣關係的子女資訊

    Args:
        w: 母親姓名

    Returns:
        None
    """
    global all_members
    global g_loc

    # search for kids whose Mom has the name, called 'w'
    filter = "Mom == @w"
    kids = all_members.query(filter)
    if kids.empty:
        # no kids found
        return

    # Kids found
    # drop duplocated row with the same name, birth-year and relation
    kids = kids.drop_duplicates(subset=["Name", "Born", "Relation"], keep="first")

    # loop thru to retrieve kid's info
    cnt_k = len(kids.index)
    for i, k in zip(range(cnt_k), kids.Name):
        born = int(kids.Born.iloc[i]) if pd.notna(kids.Born.iloc[i]) else 0
        died = int(kids.Died.iloc[i]) if pd.notna(kids.Died.iloc[i]) else 0
        kid_sex = g_lsex[kids.Sex.iloc[i]]
        kid_rel = g_lrelation[kids.Relation.iloc[i]]
        kid_label = f"{k} {born}-{died}"
        kid_href = kids.Href.iloc[i] if pd.notna(kids.Href.iloc[i]) else ""

        # associate different emoji with both male and female
        if kid_sex == g_loc["SEX_MALE"] or kid_sex == g_loc["SEX_INLAW_MALE"]:
            # kid is male
            desc = f"#### ===> :sunglasses: ({kid_rel}): [{kid_label}]({kid_href})"
        else:
            # kid is female
            desc = f"#### ===> :last_quarter_moon_with_face: ({kid_rel}): [{kid_label}]({kid_href})"

        # display kid's info
        st.markdown(desc)
    return


# Display a list of members who are related to members who are within
# three generations via Streamlit.
def display_3gen(dmem):
    """
    透過Streamlit顯示與成員在三代範圍內相關的成員列表

    Args:
        dmem (dict): 包含成員資訊的字典

    Returns:
        None
    """
    global g_loc
    global g_lsex

    mem = dmem["Name"]
    born = dmem["Born"]
    # format the basic info about member
    mem_label = f"{mem} {born}-{dmem['Died']}"
    desc = f"### {mem_label} [{dmem['Href']}]({dmem['Href']})"

    # if given member is not male, show extra info:
    #   1. her marriage year
    #   2. associated kids if any
    msex = g_lsex[dmem["Sex"]]
    if msex != g_loc["SEX_MALE"] and msex != g_loc["SEX_INLAW_MALE"]:
        desc = desc + f", {g_loc['MARRIED_IN']}{dmem['Married']}"
        st.markdown(desc)
        # search for her kids to display
        display_kids(mem)
    else:
        st.markdown(desc)

    display_dad(dmem)
    display_mom(dmem)
    display_spouse(dmem)
    return


# 顯示成員的詳細資訊並處理更新
def display_update_member():
    """
    這個函數會在網頁上：
        1. 以行-列布局顯示欄位
        2. 請求用戶進行更新

    Returns:
        None
    """
    global g_loc, gbuff

    # row 1
    c11, c12, c13 = st.columns([3, 2, 2])
    gbuff["Name"] = c11.text_input(
        f":blue[{g_loc['L311_FULL_NAME']}]",
        gbuff["Name"],
        max_chars=20,
        help=g_loc["L311_HELP"],
    )
    gbuff["Aka"] = c12.text_input(
        f":blue[{g_loc['L312_ALIAS']}]",
        gbuff["Aka"],
        max_chars=60,
        help=g_loc["L312_HELP"],
    )

    rec_sex = c13.selectbox(
        f":blue[{g_loc['L313_SEX']}]",
        options=g_lsex,
        index=int(gbuff["Sex"]),
        help=g_loc["L313_HELP"],
    )
    gbuff["Sex"] = g_lsex.index(rec_sex)

    today = datetime.date.today()

    # row 2
    c21, c22, c23 = st.columns([3, 2, 2])
    gbuff["Order"] = c21.number_input(
        f":blue[{g_loc['L321_GEN_ID']}]",
        gbuff["Order"],
        today.year,
        help=g_loc["L321_HELP"],
    )
    gbuff["Born"] = c22.number_input(
        f":blue[{g_loc['L322_BIRTH_YEAR']}]",
        gbuff["Born"],
        today.year,
        help=g_loc["L322_HELP"],
    )
    gbuff["Died"] = c23.number_input(
        f":blue[{g_loc['L323_DEATH_YEAR']}]",
        gbuff["Died"],
        today.year,
        help=g_loc["L323_HELP"],
    )

    # row 3
    c31, c32, c33 = st.columns([3, 2, 2])
    gbuff["Dad"] = c31.text_input(
        f":blue[{g_loc['L331_DAD_NAME']}]",
        gbuff["Dad"],
        max_chars=20,
        help=g_loc["L331_HELP"],
    )
    gbuff["Mom"] = c32.text_input(
        f":blue[{g_loc['L332_MOM_NAME']}]",
        gbuff["Mom"],
        max_chars=20,
        help=g_loc["L332_HELP"],
    )
    rec_rel = c33.selectbox(
        f":blue[{g_loc['L333_RELATION']}]",
        options=g_lrelation,
        index=int(gbuff["Relation"]),
        help=g_loc["L333_HELP"],
    )
    gbuff["Relation"] = g_lrelation.index(rec_rel)

    # row 4
    c41, c42, c43 = st.columns([2, 3, 2])
    rec_status = c41.selectbox(
        f":blue[{g_loc['L341_STATUS']}]",
        options=g_lstatus,
        index=int(gbuff["Status"]),
        help=g_loc["L341_HELP"],
    )
    gbuff["Status"] = g_lstatus.index(rec_status)

    gbuff["Spouse"] = c42.text_input(
        f":blue[{g_loc['L342_SPOUSE']}]",
        gbuff["Spouse"],
        max_chars=20,
        help=g_loc["L342_HELP"],
    )

    gbuff["Married"] = c43.number_input(
        f":blue[{g_loc['L343_MARRIAGE_YEAR']}]",
        gbuff["Married"],
        today.year,
        help=g_loc["L343_HELP"],
    )

    # row 5
    c51, _ = st.columns([6, 1])
    gbuff["Href"] = c51.text_input(
        f":blue[{g_loc['L351_URL']}]",
        gbuff["Href"],
        max_chars=120,
        help=g_loc["L351_HELP"],
    )

    return


# Return a Pandas dataframe obj
def get_gen(gen_begin, num):
    """
    獲取從指定代數開始的多代成員資料

    Args:
        gen_begin (int): 開始的代數
        num (int): 要獲取的代數範圍

    Returns:
        pandas.DataFrame: 包含成員資料的數據框

    Raises:
        FileNotFoundError: 當找不到資料時
    """
    gen_begin + num

    filter = "Order >= @gen_begin and Order <= @gen_end"
    target_members = all_members.query(filter)
    if target_members.empty:
        # no members found in this generation
        raise (FileNotFoundError)

    target_members = target_members.sort_values(["Order", "Born"])
    return target_members


# A generator function, yielding an unique member at a time,
# given a member-name.
def get_umember(name, spouse="?", dad="?", mom="?", born="0", order="0"):
    """
    獲取指定條件的唯一成員

    Args:
        name (str): 成員姓名（必填）
        spouse (str, optional): 配偶姓名. Defaults to "?".
        dad (str, optional): 父親姓名. Defaults to "?".
        mom (str, optional): 母親姓名. Defaults to "?".
        born (str, optional): 出生年. Defaults to "0".
        order (str, optional): 代數順序. Defaults to "0".

    Returns:
        tuple: 包含成員索引和相關字典物件的生成器

    Raises:
        FileNotFoundError: 當找不到符合條件的成員時
    """
    global all_members, g_loc

    # build filter
    filter = "Name == @name"
    if spouse != "?":
        filter = filter + " and Spouse == @spouse"
    if dad != "?":
        filter = filter + " and Dad == @dad"
    if mom != "?":
        filter = filter + " and Mom == @mom"
    if born != "0":
        born = int(born)
        filter = filter + " and Born == @born"
    if order != "0":
        order = int(order)
        filter = filter + " and Order == @order"

    # retrieve matched members into a dataframe
    all_members['Name'] = all_members['Name'].astype(str)
    all_members['Dad'] = all_members['Dad'].astype(str)
    all_members['Mom'] = all_members['Mom'].astype(str)
    rec = all_members.query(filter)
    if rec.empty:
        raise (FileNotFoundError)

    logger.debug(f"Found Member: {rec}")

    didx = rec.to_dict("index")
    for i in didx:
        # yield one member (row index and its dictionary) at a time
        yield i, didx[i]


# --- Main Web Widget --- from here
@func_timer_decorator
def main_page(nav, lname_idx):
    """
    主頁面控制函數，根據側邊欄選項顯示相應內容

    Args:
        nav (str): 選擇的導航選項
        lname_idx (dict): 姓氏索引字典

    Returns:
        None
    """
    global g_username, g_lname
    global gbuff, gbuff_idx
    global g_loc, g_loc_key, g_L10N_options, g_L10N
    global g_df
    global g_fTree, g_path_dir
    global g_dirtyUser, g_dirtyTree

    # --- Function 1 --- from here
    # display a family graph by selected male-member
    if nav == g_loc["MENU_DISP_GRAPH_BY_MALE"]:
        # display a family graph starting from a male-member
        # selected with associated spousees who have related kids

        st.subheader(g_loc["T1_DISP_GRAPH_BY_MALE"])

        if lname_idx <= 0:
            # at least 2 generations
            st.error(f"❌ {g_loc['MENU_DISP_GRAPH_BY_MALE']} {g_loc['QUERY']} {g_loc['GEN_AT_LEAST_2']}")
            return

        # select a generation
        max_gen = load_male_gen(g_lname, base=g_dirtyTree)
        default_gen = gbuff["Order"]

        fgen = st.slider(
            g_loc["S1_GEN_ORDER"], 0, max_gen, default_gen, help=g_loc["S1_HELP"]
        )

        c11, c12 = st.columns([5, 5])
        today = datetime.date.today()
        max_year = today.year
        default_year = today.year - 100
        fborn1 = c11.slider(
            g_loc["S1_BORN_FROM"],
            0,
            max_year,
            default_year,
            step=10,
            help=g_loc["S1_HELP"],
        )

        default_year = today.year
        fborn2 = c12.slider(
            g_loc["S1_BORN_TO"],
            0,
            max_year,
            default_year,
            step=10,
            help=g_loc["S1_HELP"],
        )

        try:
            # build a male list of tuples, given selected generation
            lname = slice_male_list(fgen, fborn1, fborn2, base=g_dirtyTree)
            lname_idx = len(lname) - 1
            tmem = st.selectbox(
                g_loc["L1_SELECTBOX"],
                options=lname,
                index=lname_idx,
                help=g_loc["L1_HELP"],
            )
            logger.debug(f"Selected Tuple= {tmem}")
            order, mem, born = tmem
            lname_idx = lname.index(tmem)
            st.markdown(f"{g_loc['HEAD_COUNT_SELECTED']}{len(lname)}")

            try:
                memgen = get_umember(mem, order=order, born=born)
                for idx, gbuff in memgen:
                    mem = gbuff["Name"]
                    born = gbuff["Born"]
                    order = gbuff["Order"]
                    sex = g_lsex[gbuff["Sex"]]
                    st.markdown(
                        f"#### {g_loc['GEN_ORDER']}: {order} {g_loc['MEMBER']} {g_loc['INDEX']}: {idx} {mem}({born},{sex})"
                    )
                    gbuff_idx = idx
                    break

                # build the graph using the first member got
                logger.debug(f"gbuff={gbuff}\ngbuff_idx={gbuff_idx}")
                load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)

                dot = build_spouse_graph(gbuff)
            except Exception:
                st.error(f"❌ {g_loc['MEMBER_NOT_FOUND']}")
                return

            # Show graph on Streamlit Page
            logger.debug(dot.source)
            st.graphviz_chart(dot, use_container_width=True)

        except Exception:
            st.warning(f"⚠️ {g_loc['MEMBER_NOT_FOUND']}")
            # continue to adjust sliders

        st.success(
            f"{g_loc['MENU_DISP_GRAPH_BY_MALE']} {g_loc['QUERY']} {g_loc['DONE']}"
        )
        return

    # --- Function 2 --- from here
    # list a family info by male-member
    if nav == g_loc["MENU_QUERY_3G_BY_MALE"]:
        # list immediate family basic info with respect to a
        # given a tuple (male-member -name, birth-year)
        st.subheader(g_loc["T2_QUERY_3G_BY_MALE"])

        if lname_idx <= 0:
            # at least 2 generations
            st.error(f"❌ {g_loc['MENU_QUERY_3G_BY_MALE']} {g_loc['QUERY']} {g_loc['GEN_AT_LEAST_2']}")
            return

        # select a generation

        max_gen = load_male_gen(g_lname, base=g_dirtyTree)
        default_gen = gbuff["Order"]

        fgen = st.slider(
            g_loc["S1_GEN_ORDER"], 0, max_gen, default_gen, help=g_loc["S1_HELP"]
        )

        c11, c12 = st.columns([5, 5])
        today = datetime.date.today()
        max_year = today.year
        default_year = today.year - 100

        fborn1 = c11.slider(
            g_loc["S1_BORN_FROM"],
            0,
            max_year,
            default_year,
            step=10,
            help=g_loc["S1_HELP"],
        )

        default_year = today.year
        fborn2 = c12.slider(
            g_loc["S1_BORN_TO"],
            0,
            max_year,
            default_year,
            step=10,
            help=g_loc["S1_HELP"],
        )

        try:
            # build a male list, given selected generation
            lname = slice_male_list(fgen, fborn1, fborn2, base=g_dirtyTree)
            lname_idx = len(lname) - 1
            tmem = st.selectbox(
                g_loc["L1_SELECTBOX"],
                options=lname,
                index=lname_idx,
                help=g_loc["L1_HELP"],
            )
            order, mem, born = tmem
            lname_idx = lname.index(tmem)
            st.markdown(f"{g_loc['HEAD_COUNT_SELECTED']}{len(lname)}")

            try:
                memgen = get_umember(mem, order=order, born=born)
                for idx, gbuff in memgen:
                    mem = gbuff["Name"]
                    born = gbuff["Born"]
                    order = gbuff["Order"]
                    sex = g_lsex[gbuff["Sex"]]
                    st.markdown(
                        f"#### {g_loc['GEN_ORDER']}: {order} {g_loc['MEMBER']} {g_loc['INDEX']}:{idx} {mem}({born},{sex})"
                    )
                    break
            except Exception:
                st.error(f"❌ {g_loc['MENU_QUERY_3G_BY_MALE']} {g_loc['QUERY']} {g_loc['FAILED']}")
                return

            # display current generation, plus one level up and down
            display_3gen(gbuff)
            load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)
            st.success(
                f"{g_loc['MENU_QUERY_3G_BY_MALE']} {g_loc['QUERY']} {g_loc['DONE']}"
            )
        except Exception:
            st.warning(f"⚠️ {g_loc['MEMBER_NOT_FOUND']}")
            # continue to adjust sliders

        return

    # --- Function 3 --- from here
    # add a new Family Member
    if nav == g_loc["MENU_MEMBER_ADD"]:
        st.subheader(g_loc["T3_MEMBER_ADD"])

        # initialize a dict obj, 'dbuff'
        # dbuff = gbuff.copy()

        display_update_member()

        if st.button(g_loc["B3_MEMBER_ADD"]):
            with st.spinner(g_loc["IN_PROGRESS"]):
                st.write(f"{g_loc['MENU_MEMBER_ADD']}: {gbuff['Name']}")

                # create a dict object with list values from buffer 'gbuff'
                to_add = {}
                for key, value in gbuff.items():
                    if isinstance(value, str) and value == "":
                        value = "?"

                    to_add[key] = [value]

                # convert dictionary to dataframe
                to_add = pd.DataFrame.from_dict(to_add)
                try:
                    # append to the end of family tree
                    to_add.to_csv(g_fTree, mode="a", header=False, index=False)
                    st.success(
                        f"{g_loc['MENU_MEMBER_ADD']}: {gbuff['Name']} {g_loc['ADD']} {g_loc['DONE']}"
                    )
                    # force to create a new tree cache upon return
                    os.environ["DIRTY_TREE"] = str(time.time())
                    load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)

                except Exception:
                    st.error(f"❌ {g_loc['MENU_MEMBER_ADD']}: {gbuff['Name']} {g_loc['ADD']} {g_loc['FAILED']}")
        return

    # --- Function 4 --- from here
    # update an existed Family Member
    if nav == g_loc["MENU_MEMBER_UPDATE"]:
        # update an existed Family Member
        # given by the member index of dataframe
        st.subheader(g_loc["T4_MEMBER_UPDATE"])

        # default_gen = gbuff['Order']

        idx = st.text_input(
            f":blue[{g_loc['L41_MEMBER_INDEX']}]",
            gbuff_idx,
            max_chars=10,
            help=g_loc["L41_HELP"],
        )

        # Target Series obj, identified by 'idx'
        idx = int(idx)
        try:
            # safe guard in case that person not found
            rcd = g_df.iloc[idx]
        except Exception:
            st.error(f"❌ {g_loc['MEMBER_NOT_FOUND']}")
            return

        # convert to dict buffer
        gbuff = {key: value for key, value in rcd.items()}

        display_update_member()

        st.info(
            f"{g_loc['MEMBER']} {g_loc['INDEX']}: {idx} {gbuff['Name']} {g_loc['L42_CONFIRM_UPDATE']}"
        )
        btn1, btn2 = st.columns(2)
        with btn1:
            if st.button(g_loc["B4_MEMBER_UPDATE"]):
                with st.spinner(g_loc["IN_PROGRESS"]):
                    for key, value in gbuff.items():
                        # make sure default value is not empty
                        if value == "":
                            value = "?"
                        gbuff[key] = value

                        # type conversion
                        if pd.api.types.is_integer_dtype(g_df[key]):
                            gbuff[key] = int(value)
                        if pd.api.types.is_float_dtype(g_df[key]):
                            gbuff[key] = float(value)
                        if pd.api.types.is_bool_dtype(g_df[key]):
                            gbuff[key] = bool(value)

                    # To update a row, by index with a dict obj 'gbuff'
                    g_df.loc[idx, g_df.columns] = gbuff

                    try:
                        write_tree_csv(g_fTree, g_fTree_Backup, g_df)
                        # force to create a new tree cache upon return
                        os.environ["DIRTY_TREE"] = str(time.time())
                        load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)
                        st.success(
                            f"{g_loc['MEMBER']} {g_loc['INDEX']}: {idx} {gbuff['Name']} {g_loc['UPDATE']} {g_loc['DONE']}"
                        )
                    except Exception:
                        st.error(f"❌ {g_loc['MEMBER']} {g_loc['UPDATE']} {g_loc['FAILED']}")
        with btn2:
            if st.button(g_loc["B4_MEMBER_DELETE"]):
                with st.spinner(g_loc["IN_PROGRESS"]):
                    # To drop a row, by index
                    g_df.drop([idx], inplace=True)

                    try:
                        write_tree_csv(g_fTree, g_fTree_Backup, g_df)
                        # force to create a new tree cache upon return
                        os.environ["DIRTY_TREE"] = str(time.time())

                        st.success(f"{g_loc['MEMBER']} {g_loc['INDEX']}: {idx} {gbuff['Name']} {g_loc['DELETE']} {g_loc['DONE']}")
                    except Exception:
                        st.error(f"❌ {g_loc['MEMBER']} {g_loc['DELETE']} {g_loc['FAILED']}")
        gbuff_idx = idx
        return

    # --- Function 5 --- from here
    # inquire the basic info across 3 generations by mamber-name
    if nav == g_loc["MENU_QUERY_TBL_BY_NAME"]:
        # ALl member detail info of three generations,
        #     given by any member name of the middle generation.

        st.subheader(g_loc["T5_QUERY_TBL_BY_NAME"])

        rec_name = st.text_input(
            g_loc["L51_FULL_NAME"], gbuff["Name"], max_chars=20, help=g_loc["L51_HELP"]
        )

        if st.button(g_loc["B5_MEMBER_INQUERY"]):
            with st.spinner(g_loc["IN_PROGRESS"]):
                filter = "Name == @rec_name"
                all_members['Name'] = all_members['Name'].astype(str)
                df2 = g_df.query(filter)
                if df2.empty:
                    st.error(f"❌ {rec_name} {g_loc['MENU_QUERY_TBL_BY_NAME']} {g_loc['FAILED']}")
                else:
                    st.markdown(f"{g_loc['HEAD_COUNT_SELECTED']}{len(df2.index)}")
                    st.table(df2)

                    # keep the first record found, given the newly entered name
                    gbuff["Name"] = rec_name
                    gbuff["Born"] = df2.Born.iloc[0]
                    load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)
                    gbuff_idx = df2.index[0]
                    st.success(
                        f"{rec_name} {g_loc['MENU_QUERY_TBL_BY_NAME']} {g_loc['DONE']}"
                    )
        return

    # --- Function 6: --- from here
    # inquire the detail info of members by alias(es)
    if nav == g_loc["MENU_QUERY_TBL_BY_ALIAS"]:
        st.subheader(g_loc["T6_QUERY_TBL_BY_ALIAS"])

        rec_aka = st.text_input(
            g_loc["L61_ALIAS"], gbuff["Name"], max_chars=120, help=g_loc["L61_HELP"]
        )

        if st.button(g_loc["B6_MEMBER_INQUERY"]):
            with st.spinner(g_loc["IN_PROGRESS"]):
                l_grp = rec_aka.split(",")
                filter = "Aka.str.contains ("
                for w in l_grp:
                    # strip off leading and trailing spaces
                    kw = w.strip()
                    filter = filter + f"'{kw}',"

                # finally, add case insensitive search
                rec_grp = filter + " case=False)"

                logger.debug(f"Query: {rec_grp}")

                # drops NA-value rows
                df2 = g_df.dropna()
                try:
                    df2 = df2.query(rec_grp)
                    if df2.empty:
                        st.error(f"❌ {g_loc['MENU_QUERY_TBL_BY_ALIAS']} {g_loc['FAILED']}")
                    else:
                        st.markdown(f"{g_loc['HEAD_COUNT_SELECTED']}{len(df2.index)}")
                        st.table(df2)
                        gbuff["Name"] = df2["Name"].iloc[0]
                        gbuff["Born"] = df2["Born"].iloc[0]
                        load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)
                        st.success(
                            f"{g_loc['MENU_QUERY_TBL_BY_ALIAS']} {g_loc['DONE']}"
                        )
                except Exception as err:
                    logger.error(err)
                    st.error(f"❌ {g_loc['MENU_QUERY_TBL_BY_ALIAS']} {g_loc['FAILED']}")
        return

    # --- Function 7 --- from here
    # inquire the detail info of members by generation-id
    if nav == g_loc["MENU_QUERY_TBL_BY_1GEN"]:
        st.subheader(g_loc["T7_QUERY_TBL_BY_1GEN"])

        st.markdown(f"{g_loc['HEAD_COUNT_TOTAL']}{len(bio_members.index)}")
        st.markdown(f"{g_loc['HEAD_COUNT_MALE']}{len(m_members.index)}")

        # set an upper bound above the max gen order
        max_gen = load_male_gen(g_lname, base=g_dirtyTree)

        if max_gen <= 0:
            # at least 1 generation
            st.error(f"❌ {g_loc['MENU_QUERY_TBL_BY_1GEN']} {g_loc['QUERY']} {g_loc['MEMBER_NOT_FOUND']}")
            return

        default_gen = gbuff["Order"]

        gen = st.slider(
            g_loc["S1_GEN_ORDER"], 0, max_gen, default_gen, help=g_loc["S1_HELP"]
        )

        st.markdown(f"{g_loc['L711_GEN_FROM']} {gen} {g_loc['L712_GEN_TO']}")
        try:
            # list current generation
            g1_members = get_gen(gen, 0)
            st.markdown(f"{g_loc['HEAD_COUNT_SELECTED']}{len(g1_members.index)}")
            st.table(g1_members)
            load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)
            st.success(f"{g_loc['MENU_QUERY_TBL_BY_1GEN']} {g_loc['DONE']}")
        except Exception:
            st.error(f"❌ {g_loc['MENU_QUERY_TBL_BY_1GEN']} {g_loc['FAILED']}")
        return

    # --- Function 8 --- from here
    # inquire the basic info of members by member-name etc.
    if nav == g_loc["MENU_QUERY_3G_BY_NAME"]:
        # inquire the basic info of members by member-name (mandatory)
        # and two optional attributes:
        # 1. bith-year,
        # 2. spouse

        st.subheader(g_loc["T8_QUERY_3G_BY_NAME"])

        rec_name = st.text_input(
            g_loc["L81_ENTER_NAME"], gbuff["Name"], max_chars=20, help=g_loc["L81_HELP"]
        )

        c11, c12 = st.columns([4, 6])
        rec_born = c11.text_input(
            g_loc["L82_ENTER_BORN"], "0", max_chars=20, help=g_loc["L82_HELP"]
        )

        rec_spouse = c12.text_input(
            g_loc["L83_ENTER_SPOUSE"], "?", help=g_loc["L83_HELP"]
        )

        if st.button(g_loc["B8_QUERY_3G"]):
            try:
                # keep the new entered name
                gbuff["Name"] = rec_name
                load_buff(gbuff["Name"], gbuff["Born"], g_dirtyTree)

                memgen = get_umember(rec_name, spouse=rec_spouse, born=rec_born)
                for idx, dmem in memgen:
                    mem = dmem["Name"]
                    born = dmem["Born"]
                    gbuff["Born"] = born
                    gbuff_idx = idx
                    order = dmem["Order"]
                    sex = g_lsex[dmem["Sex"]]
                    st.markdown(
                        f"#### {g_loc['GEN_ORDER']}:{order} {g_loc['MEMBER']} {g_loc['INDEX']}:{idx} {mem}({born},{sex})"
                    )
                    display_3gen(dmem)
                    st.markdown("---")
                    gbuff = dmem.copy()
                st.success(f"{rec_name} {g_loc['MENU_QUERY_3G_BY_NAME']} {g_loc['DONE']}")
            except Exception:
                st.error(f"❌ {rec_name} {g_loc['MENU_QUERY_3G_BY_NAME']} {g_loc['FAILED']}")
        return

    # --- Function 9 --- from here
    # list the detail info of 3-generation view
    if nav == g_loc["MENU_QUERY_TBL_BY_3GEN"]:
        # list the detail info of 3-generation view, given by
        # member-name
        st.subheader(g_loc["T9_QUERY_TBL_BY_3GEN"])

        st.markdown(f"{g_loc['HEAD_COUNT_TOTAL']}{len(bio_members.index)}")
        st.markdown(f"{g_loc['HEAD_COUNT_MALE']}{len(m_members.index)}")

        # select a begining generation and list 2 generations below
        max_gen = load_male_gen(g_lname, base=g_dirtyTree)
        if max_gen <= 1:
            # at least 2 generations
            st.error(f"❌ {g_loc['MENU_QUERY_TBL_BY_3GEN']} {g_loc['QUERY']} {g_loc['MEMBER_NOT_FOUND']}")
            return

        default_gen = gbuff["Order"]

        gen = st.slider(
            g_loc["S1_GEN_ORDER"], 0, max_gen, default_gen, help=g_loc["S1_HELP"]
        )

        try:
            st.markdown(f"{g_loc['L911_GEN_FROM']} {gen} {g_loc['L912_GEN_TO']}")
            # current + 2 = 3 generations
            g3_members = get_gen(gen, 2)
            st.markdown(f"{g_loc['HEAD_COUNT_SELECTED']}{len(g3_members.index)}")
            st.table(g3_members)
            st.success(f"{g_loc['MENU_QUERY_TBL_BY_3GEN']} {g_loc['DONE']}")
        except Exception:
            st.error(f"❌ {g_loc['MENU_QUERY_TBL_BY_3GEN']} {g_loc['FAILED']}")
        return

    # --- Function 10 --- from here
    # Configure User Settings
    if nav == g_loc["MENU_SETTINGS"]:
        # Three settings are supported:
        # 1. Change User Language Setting
        # 2. Import a family tree from a CSV file and
        #   merge into the current family tree
        # 3. Export the current family tree to 
        #   a local 'Download' folder
        # 4. Export the csv to family.db SQLite DB file in data folder.
        
        st.subheader(g_loc["T10_USR_SETTINGS"])

        # create two tables in family.db if not exists
        
        # --- User L10N Settings --- from here
        c1, c2 = st.columns([3, 7])

        # User L10N setting
        g_loc_key = c1.selectbox(
            f":blue[{g_loc['SX_L10N']}]",
            options=g_L10N_options,
            index=g_L10N_options.index(g_loc_key),
            help=g_loc["SX_L10N_HELP"],
        )

        # enter CSV file name (no .csv) to export/download
        lexport = f":blue[{g_loc['BX_EXPORT_HELP']}]"
        filename = c2.text_input(lexport, placeholder=g_loc["BX_EXPORT_HELP"])

        # --- User Export CSV --- from here
        # enter a CSV file name to export/download
        with c2:
            export_path = g_fTree if os.path.isfile(g_fTree) else f"{g_path_dir}/me.sample.csv"
            if not os.path.isfile(export_path):
                st.info("No family-tree CSV is available to export. Add data/me.csv locally, or keep data/me.sample.csv.")
            else:
                with open(export_path) as f:
                    fn = f"{filename}.csv"
                    if c2.download_button(g_loc["BX_EXPORT"], f, fn):
                        st.success(f"{g_loc['BX_EXPORT']} {fn} {g_loc['DONE']}")

        # set L10N upon click
        with c1:
            if st.button(g_loc["BX_USR_SETTINGS"]):
                g_loc = g_L10N[g_loc_key]
                os.environ["L10N"] = g_loc_key
                try:
                    st.info(f"{g_loc_key}: {g_loc['LANGUAGE_MODE_AFTER_RELOAD']}")

                    # force to create a new UserDB cache upon return
                    os.environ["DIRTY_USER"] = str(time.time())
                except Exception as err:
                    fu.show_user_error("Something went wrong. Check the server log for details.", err, warn=True)
                    st.error(f"❌ {g_loc['MENU_SETTINGS']} {g_username} {g_loc['FAILED']}")

        # --- User Import CSV --- from here
        # drag and drop CSV file to import
        f = st.file_uploader(f":blue[{g_loc['BX_IMPORT_HELP']}]")

        # merge two family trees vertically upon click
        if st.button(g_loc["BX_IMPORT"]):
            with st.spinner(g_loc["IN_PROGRESS"]):
                df = pd.read_csv(f)
                if df.iloc[0].Name == "?":
                    # make sure Dataframe no placeholder row
                    mbrs = df.drop(index=0)

                if mbrs.empty:
                    return  # no merge needed

                g_df = pd.concat([g_df, mbrs])

                # make sure no duplicates
                g_df.drop_duplicates(inplace=True)

                # sort in order by Gen-Order, Birth-year, and Name
                g_df.sort_values(by=["Order", "Born", "Name"], inplace=True)

                try:
                    write_tree_csv(g_fTree, g_fTree_Backup, g_df)
                    st.success(f"{g_loc['BX_IMPORT']} {g_loc['DONE']}")

                    # force to create a new tree cache upon return
                    os.environ["DIRTY_TREE"] = str(time.time())

                except Exception:
                    st.error(f"❌ {g_loc['BX_IMPORT']} {g_loc['FAILED']}")
    return


# ---- READ Family Tree from CSV ----
# Clear all caches every 5 min = 300 seconds
def write_tree_csv(path, backup, frame):
    """Write a family-tree CSV. Back up the personal file when it already exists."""
    if os.path.isfile(path):
        os.replace(path, backup)
    frame.to_csv(path, mode="w", header=True, index=False)


@st.cache_data(ttl=300)
def get_data_from_csv(f, base=None):
    """
    Read a family-tree CSV.

    The first data row is a placeholder and is omitted from the members frame.
    A missing or unreadable file returns (None, None) so the caller can show
    an empty state instead of creating data/me.csv.
    """
    path = Path(f)
    if not path.is_file():
        logger.info("%s is not present.", f)
        return None, None
    try:
        df = pd.read_csv(path)
    except Exception:
        logger.exception("Failed to read %s", f)
        return None, None
    if df.empty:
        return df, df.iloc[0:0]
    members = df.drop(index=df.index[0])
    logger.debug("%s LOADED.", f)
    return df, members


# --- Selecting records from all family members --- from here
@st.cache_data(ttl=300)
def load_dataframe(members, rel, base=None):
    """
    載入所有家庭成員的記錄

    Args:
        members (pandas.DataFrame): 成員數據框
        rel (str): 關係類型
        base (str, optional): 基準路徑. Defaults to None.

    Returns:
        pandas.DataFrame: 處理後的 Pandas DataFrame
    """
    filter = "Relation == @rel"
    df1 = members.query(filter).sort_values(by=["Order", "Born"])
    return df1


# --- Load up Male Members --- from here
@st.cache_data(ttl=300)
def load_male_gen(lname, base=None):
    """
    載入男性成員列表

    Args:
        lname (list of tuples): 男性成員列表，每個元組包含 (代數順序, 姓名, 出生年)
        base (str, optional): 基準路徑. Defaults to None.

    Returns:
        int: 最新一代的代數順序
    """
    if not lname:
        return 0
    order, _, _ = lname[-1]
    return order


# --- Load Male Members into list of tuples --- from here
@st.cache_data(ttl=300)
def slice_male_list(order, born1, born2, base=None):
    """
    根據代數和出生年份範圍篩選男性成員列表

    Args:
        order (str): 代數順序
        born1 (str): 起始出生年
        born2 (str): 結束出生年
        base (str, optional): 基準路徑. Defaults to None.

    Returns:
        list: 符合條件的男性成員列表
    """
    global g_lname

    lname = []
    born1 = int(born1)
    born2 = int(born2)
    for o, m, b in g_lname:
        b = int(b)
        if o == order and b >= born1 and b <= born2:
            lname.append((o, m, b))
    return lname


# --- Load up Male Members --- from here
@st.cache_data()
def load_male_members(members, base=None):
    """
    載入男性成員資料

    Args:
        members (pandas.DataFrame): 成員數據框
        base (str, optional): 基準路徑. Defaults to None.

    Returns:
        tuple: 包含男性成員數據框、姓氏列表和姓氏索引的元組
    """
    global g_loc, g_lsex
    global g_df, g_dirtyTree

    m_members = members.drop_duplicates(
        subset=["Order", "Name", "Dad", "Born"], keep="first"
    )

    # sorted by birth-year in accending order.
    g_lsex.index(g_loc["SEX_MALE"])
    g_lsex.index(g_loc["SEX_INLAW_MALE"])

    m_members = m_members.query("Sex == @male1 or Sex == @male2").sort_values(
        by=["Order", "Born", "Name"]
    )

    if m_members.empty:
        g_lname = []
        lname_idx = -1

        # initialize with the last person in dataframe
        mem = g_df.tail(1).Name.iloc[0]
        born = g_df.tail(1).Born.iloc[0]
    else:
        # create the global name list of all male-members.
        g_lname = [
            (o, m, b)
            for o, m, b in zip(m_members.Order, m_members.Name, m_members.Born)
        ]

        # initialize index to the latest joined male member, i.e.
        # the end of g_lname list
        lname_idx = len(g_lname) - 1
        logger.debug(f"lname_idx={lname_idx}")

        mem = m_members.tail(1).Name.iloc[0]
        born = m_members.tail(1).Born.iloc[0]

    load_buff(mem, born, base=g_dirtyTree)
    return m_members, g_lname, lname_idx


# --- Load up Buffer (name and born-year) into environment --- from here
@st.cache_data()
def load_buff(mem, born, base=None):
    """
    將緩衝區（姓名和出生年）載入環境中

    Args:
        mem (str): 成員姓名
        born (str): 出生年
        base (str, optional): 基準路徑. Defaults to None.
    """
    # save to environemnt
    os.environ["FT_NAME"] = mem
    os.environ["FT_BORN"] = str(born)
    return


# --- Load up User L10N --- from here
@st.cache_data(ttl=300)
def load_user_l10n(base=None):
    """
    載入用戶本地初始化設置

    Args:
        base (str, optional): 基準路徑. Defaults to None.

    Returns:
        tuple: 包含語言鍵和語言字典的元組
    """
    # --- Initialize System L10N Settings ---- from here
    # set system L10N setting as default locator key , 'g_loc_key'
    # and associated language dictionary, 'g_loc'

    g_loc_key = os.getenv("L10N", "繁中").strip('"\'').upper()
    g_loc = g_L10N[g_loc_key]
    logger.debug(f"g_loc_key={g_loc_key}")
    logger.debug(f"g_loc={g_loc}")
    return g_loc_key, g_loc


# Initialize session state
cu.init_session_state()
cu.apply_ui_preferences()
    
# Check authentication
if not st.session_state.get('authenticated', False):
    st.switch_page("fTrees.py")
else:
    st.empty()

    g_dirtyTree = os.getenv("DIRTY_TREE", "0")
    logger.debug(f"DIRTY_TREE: {g_dirtyTree}")

    g_dirtyUser = os.getenv("DIRTY_USER", "0")
    logger.debug(f"DIRTY_USER: {g_dirtyUser}")

    # --- global L10N dictionary --- from here
    # Load 'g_L10N', for all languages
    # Load global list, 'g_L10N_options', for all languages
    g_L10N = fu.load_L10N(base=g_dirtyUser)
    g_L10N_options = list(g_L10N.keys())

    # --- Load User L10N --- from here
    g_loc_key, g_loc = load_user_l10n(base=g_dirtyUser)

    # logging check-points --- here
    logger.debug(f"{g_loc['SVR_LOGGING']}: {g_logging}")
    logger.debug(f"{g_loc['SVR_L10N']}: {g_loc_key}")

    # Set default user's L10N settings
    g_username = "me"
    g_fullname = "Personal Edition"

    # Set user-specific L10N dict obj
    g_loc = g_L10N[g_loc_key]
    logger.debug(f"{g_loc['SX_L10N']}: {g_loc_key}")

    # ---- SIDEBAR ---- from here
    with st.sidebar:
        if st.session_state.user_state != dbm.User_State['p_admin']:
            # Hide the default navigation for non-padmin users
            st.markdown("""
            <style>
                [data-testid="stSidebarNav"] {
                    display: none !important;
                }
            </style>""", unsafe_allow_html=True)
        
        if 'user_email' in st.session_state and st.session_state.user_email:
            st.markdown(
                f"<div style='background-color: #2e7d32; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 1rem;'>"
                f"<p style='color: white; margin: 0; font-weight: bold; text-align: center;'>{st.session_state.user_email}</p>"
                "</div>",
                unsafe_allow_html=True)
            cu.update_context({
                'email_user': st.session_state.user_email
            })
        
        if st.session_state.user_state != dbm.User_State['p_admin']:
            # Page Navigation Links
            st.subheader("Navigation")
            st.page_link("fTrees.py", label="Home", icon="🏠")
            st.page_link("pages/3_csv_editor.py", label="CSV Editor", icon="🔧")
            st.page_link("pages/4_json_editor.py", label="JSON Editor", icon="🪛")
            st.page_link("pages/6_show_3G.py", label="Show 3 Generations", icon="👥")
            st.page_link("pages/7_show_related.py", label="Show Related", icon="👨‍👩‍👧‍👦")
            if st.session_state.user_state == dbm.User_State['f_admin']:
                st.page_link("pages/2_famMgmt.py", label="Family Tree Management", icon="🌲")
        
        # Add logout button at the bottom
        if st.button("Logout", type="primary", use_container_width=True, key="ftpe_logout"):
            # Log logout activity
            if 'user_email' in st.session_state and st.session_state.user_email:
                fu.log_activity(st.session_state.user_email, 'logout')
            st.session_state.authenticated = False
            st.session_state.user_email = None
            st.rerun()
            
        # Define the title of sidebar widget
        g_SBAR_TITLE = (
            f"{g_fullname}{g_loc['FAMILY_TREE']}\n## {g_loc['WELCOME']} {g_fullname}"
        )
        st.title(g_SBAR_TITLE)
        
        # Show side-bar 9 functions
        nav = st.radio(
            g_loc["MENU_TITLE"],
            [
                g_loc["MENU_DISP_GRAPH_BY_MALE"],
                g_loc["MENU_QUERY_3G_BY_MALE"],
                g_loc["MENU_MEMBER_ADD"],
                g_loc["MENU_MEMBER_UPDATE"],
                g_loc["MENU_QUERY_TBL_BY_NAME"],
                g_loc["MENU_QUERY_TBL_BY_ALIAS"],
                g_loc["MENU_QUERY_TBL_BY_1GEN"],
                g_loc["MENU_QUERY_3G_BY_NAME"],
                g_loc["MENU_QUERY_TBL_BY_3GEN"],
                g_loc["MENU_SETTINGS"],
                ],
            )
                                    
   # ---- SIDEBAR ---- end here

    # Define global repository settings
    g_path_dir = Path(__file__).parent.parent.resolve() / "data"
    g_fTree = f"{g_path_dir}/{g_username}.csv"
    g_fTree_template = f"{g_path_dir}/template.csv"
    g_fTree_Backup = f"{g_path_dir}/{g_username}_bak.csv"
    g_sample = f"{g_path_dir}/me.sample.csv"

    g_df, all_members = get_data_from_csv(g_fTree, base=g_dirtyTree)
    if g_df is None:
        st.warning(
            "data/me.csv is not on this machine. Personal family trees stay local and are not stored in git. "
            "Showing the fictional sample at data/me.sample.csv. Copy that file to data/me.csv to keep your own tree."
        )
        g_df, all_members = get_data_from_csv(g_sample, base=g_dirtyTree)
    if g_df is None or all_members is None:
        st.error(
            "No family-tree CSV could be loaded. Add data/me.csv, or restore the fictional data/me.sample.csv."
        )
        st.stop()

    # Define global list, 'g_lview', used for inquery
    g_lview = [g_loc["VIEW_NAME"], g_loc["VIEW_STATUS"], g_loc["VIEW_RECORD"]]

    # Define global list, 'g_lsex', containing member sex info
    # NOTE: The list order must NOT be changed,
    #   since the list index is used to store in the family tree.
    g_lsex = [
        g_loc["SEX_MALE"],
        g_loc["SEX_FEMALE"],
        g_loc["SEX_INLAW_MALE"],
        g_loc["SEX_INLAW_FEMALE"],
    ]

    # Define golbal list, 'g_lrelation',
    #   containing relationship between member and parents
    # NOTE: The list order must NOT be changed,
    #   since the list index is used to store in the family tree.
    g_lrelation = [g_loc["REL_BIO"], g_loc["REL_ADOPT"], g_loc["REL_STEP"]]

    # Define golbal list, 'g_lstatus',
    #   containing relationship between member and spouse
    # NOTE: The list order must stay un-changed once family tree initialized,
    #   since the list index is used as value to store in the family tree.
    g_lstatus = [g_loc["REL_SINGLE"], g_loc["REL_MARRIED"], g_loc["REL_TOGETHER"]]

    # Define global variables
    # Define a global 'Single Status' vaiable, 'g_single'
    g_single = g_lstatus.index(g_loc["REL_SINGLE"])

    # Define a global dataframe 'adopt_members' for adopted members
    rel = g_lrelation.index(g_loc["REL_ADOPT"])
    adopt_members = load_dataframe(all_members, rel, base=g_dirtyTree)

    # Define a global dataframe 'step_members' for step-members
    rel = g_lrelation.index(g_loc["REL_STEP"])
    step_members = load_dataframe(all_members, rel, base=g_dirtyTree)

    # Define a global dataframe, 'bio_members' for bio-members
    rel = g_lrelation.index(g_loc["REL_BIO"])
    bio_members = load_dataframe(all_members, rel, base=g_dirtyTree)

    # Define a global list of male members, 'g_lname'
    # and its index, 'lname_idx'
    m_members, g_lname, lname_idx = load_male_members(all_members, base=g_dirtyTree)
    logger.debug(f"lname_idx={lname_idx}")

    # retrieve from environment
    mem = os.getenv("FT_NAME")
    born = int(os.getenv("FT_BORN"))

    try:
        # initialize a global member index, 'gbuff_idx' as template.
        # initialize a global dict obj, 'gbuff' as template.
        gbuff_idx, gbuff = fu.get_1st_mbr_dict(g_df, mem, born, base=g_dirtyTree)
    except Exception:
        # force to create a new tree cache upon loop-back
        os.environ["DIRTY_TREE"] = str(time.time())
        st.warning(f"⚠️ {g_loc['MEMBER_NOT_REG']}")

    # Invoke main page via Streamlit
    main_page(nav, lname_idx)
    logger.debug(f"gbuff={gbuff}\ngbuff_idx={gbuff_idx}")
    logger.debug(f"{nav} <=== FINISHED.")

