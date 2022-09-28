import datetime
import enum
import json
import time
import telebot
from telebot import types as t
import random
from threading import Thread
import os

DATA_PATH = '/var/MireaChatBotData/'


def loadPresetSettings():
    if os.path.exists(DATA_PATH + 'credentials.json'):
        credentialsFile = open(DATA_PATH + 'credentials.json', 'r')
        credentialsData = json.load(credentialsFile)
        global token
        token = credentialsData['token']
        credentialsFile.close()
    if os.path.exists(DATA_PATH + 'group_data.json'):
        global groupInfo
        groupDataFile = open(DATA_PATH + 'group_data.json', 'r')
        groupData = json.load(groupDataFile)
        if isinstance(groupData['chat_id'], int) and groupData['chat_id'] != 0:
            groupInfo.ChatId = groupData['chat_id']
        if isinstance(groupData['supervisor_id'], int) and groupData['supervisor_id'] != 0:
            groupInfo.SupervisorId = groupData['supervisor_id']
        if isinstance(groupData['admin_id'], int) and groupData['admin_id'] != 0:
            groupInfo.AdminId = groupData['admin_id']
        groupDataFile.close()


def savePresetData():
    groupDataFile = open(DATA_PATH + 'group_data.json', 'w+')
    json.dump(groupInfo.GetGroupDataDict(), groupDataFile)


def getWeekNumber() -> int:
    firstWeekEnd = 6 - datetime.date(2022, 9, 1).weekday()
    currentWeek = (datetime.date.today() - datetime.date(2022, 9, firstWeekEnd)).days / 7
    return int(currentWeek)


class GroupInfo(object):
    def __init__(self, _studentAmount):
        self.LessonAmount = []
        self.ChatId = 0
        self.Students = []
        self.SupervisorId = 0
        self.AdminId = 0

    def GetGroupDataDict(self):
        res = dict()
        res['chat_id'] = self.ChatId
        res['admin_id'] = self.AdminId
        res['supervisor_id'] = self.SupervisorId
        return res


groupInfo = GroupInfo(30)
groupInfo.LessonAmount = [[2, 2, 2, 3, 3, 2, 0], [2, 2, 3, 3, 3, 2, 0]]


class StudentStatusAtLesson(enum.Enum):
    NotStated = 0
    Attended = 1
    Missed = 2


class StudentData(object):
    def __init__(self, id: int, fullName: str):
        self.UserId = id
        self.FullName = fullName
        self.internalId = 0

    def createFromDict(cls, params: dict):
        res = StudentData(0, '')
        res.UserId = params['id']
        res.FullName = params['full_name']
        res.internalId = 0
        return res

    def getParamDict(self) -> dict:
        res = dict()
        res['id'] = self.UserId
        res['full_name'] = self.FullName
        return res


class DayRecord(object):
    def __init__(self, student: StudentData, n: int):
        self.lessons = [StudentStatusAtLesson.Attended for i in range(n)]
        self.studentData = student

    def createFromDict(cls, params: dict):
        res = DayRecord(None, 0)
        res.studentData = StudentData.createFromDict(params['student'])
        res.lessons = [StudentStatusAtLesson(params['lessons'][i]) for i in range(len(params['lessons']))]
        return res

    def getDataDict(self):
        res = dict()
        res['student'] = self.studentData.getParamDict()
        res['lessons'] = [int(self.lessons[i]) for i in range(len(self.lessons))]
        return res


class DayStatistic(object):
    def __init__(self, group: GroupInfo, weekNumber: int, weekDay: int, date: datetime.date = None):
        self.records = [DayRecord(group.Students[i], group.LessonAmount[weekNumber % 2][weekDay]) for i in
                        range(len(group.Students))]
        self.date = date

    def createFromDict(cls, params: dict):
        res = DayStatistic(None, 0, 0, None)
        res.records = [DayRecord.createFromDict(params['records'][i]) for i in range(len(params['records']))]
        res.date = datetime.date.fromisoformat(params['date'])
        return res

    def getDataDict(self) -> dict:
        res = dict()
        res['records'] = [self.records[i].getDataDict() for i in range(len(self.records))]
        res['date'] = self.date.isoformat()
        return res

    def GetStudentRecordById(self, id: int) -> DayRecord:
        for rec in self.records:
            if rec.studentData.UserId == id:
                return rec


class DataRecorder(object):
    def __init__(self, _path):
        self.path = _path

    def saveData(self, data: dict):
        json.dump(data, open(self.path, 'w+'))

    def loadData(self) -> (dict, None):
        if os.path.exists(self.path):
            return json.load(self.path)
        return None

    def deleteData(self):
        if os.path.exists(self.path):
            os.remove(self.path)


class DayStatisticCollector(object):
    def __init__(self, botObj: telebot.TeleBot, groupObj: GroupInfo):
        self._bot = botObj
        self._groupInfo = groupObj
        self._restrictedPhrases = ['куратор', 'BOT']
        self.SupervisorPassword = 'SpecialForDasha'
        self.AdministratorPassword = 'asdqwerty312'
        self._todayPoll = None
        self._todayStatistic = DayStatistic(self._groupInfo, 0, 0)
        self._todayPollMessageId = 0
        self.isPollingGranted = False
        self.criticalDayDataRecorder = DataRecorder(DATA_PATH + 'day-data.json')
        data = self.criticalDayDataRecorder.loadData()
        if data is not None:
            self._todayStatistic = DayStatistic(data['stat'])
            self._todayPollMessageId = data['mes_id']

    def checkOnCompulsoryParams(self) -> bool:
        if self._groupInfo.ChatId == 0: return False
        if self._groupInfo.SupervisorId == 0: return False
        return True

    def checkOnRestrictedPhrases(self, name: str) -> bool:
        if not isinstance(name, str): return False
        if len(name) == 0: return False
        phrases = name.split()
        for phrase in phrases:
            if phrase in self._restrictedPhrases:
                return False
        return True

    def CollectDataAboutStudents(self):
        allAdmins = self._bot.get_chat_administrators(self._groupInfo.ChatId)
        for admin in allAdmins:
            if self.checkOnRestrictedPhrases(admin.custom_title):
                self._groupInfo.Students.append(StudentData(admin.user.id, admin.custom_title))
        print('Data about Students collected',
              list([self._groupInfo.Students[i].FullName for i in range(len(self._groupInfo.Students))]))
        self.isPollingGranted = True

    def getDayDataDict(self) -> dict:
        params = dict()
        params['poll_message_id'] = self._todayPollMessageId
        params['stat'] = self._todayStatistic.getDataDict()
        return params

    def setDayDataDict(self, data: dict):
        self._todayPollMessageId = data['poll_message_id']
        self._todayStatistic = DayStatistic.createFromDict(data['stat'])

    def CheckOnAdminOrSupervisorRegister(self, message: t.Message):
        if message.text == self.SupervisorPassword:
            self._groupInfo.SupervisorId = message.from_user.id
            print('New supervisor registered:', message.from_user.username)
            self._bot.send_message(message.chat.id,
                                   'Теперь ты староста группы ' + self._bot.get_chat(self._groupInfo.ChatId).title)
            self._bot.delete_message(message.chat.id, message.id)

        if message.text == self.AdministratorPassword:
            self._groupInfo.AdminId = message.from_user.id
            print('New admin registered:', message.from_user.username)
            self._bot.send_message(message.chat.id,
                                   'Теперь ты администратор группы ' + self._bot.get_chat(self._groupInfo.ChatId).title)
            self._bot.delete_message(message.chat.id, message.id)

    def GenerateDayStatisticReport(self) -> str:
        if not self.checkOnCompulsoryParams(): return ''
        resultStatisticReportText = 'Статистика отсутствующих\n\n'
        if isinstance(self._todayStatistic.date, datetime.date):
            resultStatisticReportText += 'Дата: ' + self._todayStatistic.date.strftime('%d.%m.%Y') + '\n\n'
        else:
            resultStatisticReportText += 'Дата: не установлена\n\n'
        if len(self._todayStatistic.records) == 0 or len(self._todayStatistic.records[0].lessons) == 0:
            resultStatisticReportText += 'Нет доступных данных. Если сегодня были пары, то обратись к @Alexius16 за помощью с ботом'
            print('Suspecting behavior of bot detected. Check it')
        else:
            lenLesson = len(self._todayStatistic.records[0].lessons)
            for i in range(lenLesson):
                hasMissed = False
                tempPart = 'Пара ' + str(i + 1) + '\n'
                iterator = 1
                for student in self._todayStatistic.records:
                    if student.lessons[i] == StudentStatusAtLesson.Missed:
                        tempPart += str(iterator) + '. ' + student.studentData.FullName + '\n'
                        hasMissed = True
                        iterator += 1
                if hasMissed:
                    resultStatisticReportText += tempPart
        f = open(DATA_PATH + 'reports/' + str(random.randint(1, 100000000)), 'w+')
        f.write(resultStatisticReportText)
        f.close()
        return resultStatisticReportText

    def CloseDayAndDeletePoll(self):
        if not self.checkOnCompulsoryParams(): return
        self.SendStatisticToSupervisor()
        if isinstance(self._todayPollMessageId, int) and self._todayPollMessageId != 0:
            if not self._bot.delete_message(self._groupInfo.ChatId, self._todayPollMessageId): print(
                'Failed to delete poll message')
        self.criticalDayDataRecorder.deleteData()

    def OpenDayAndSendNewPoll(self):
        if not self.checkOnCompulsoryParams(): return
        self._todayStatistic = DayStatistic(groupInfo, getWeekNumber(), (datetime.date.today().weekday() + 1) % 7,
                                            datetime.date.today() + datetime.timedelta(days=1))
        lessonLen = len(self._todayStatistic.records[0].lessons)
        if lessonLen == 0: return
        self._todayPollMessageId = self._bot.send_poll(self._groupInfo.ChatId,
                                                     'Какие пары прогуливаешь ' + self._todayStatistic.date.strftime(
                                                         '%d.%m.%Y') + '?',
                                                       ['Пара ' + str(i + 1) for i in range(lessonLen)],
                                                       is_anonymous=False, allows_multiple_answers=True).message_id
        self._bot.pin_chat_message(self._groupInfo.ChatId, self._todayPollMessageId, True)
        self.criticalDayDataRecorder.saveData(self.getDayDataDict())

    def ProcessPollAnswer(self, pollAnswer: t.PollAnswer):
        if not self.checkOnCompulsoryParams(): return
        dayRecord = self._todayStatistic.GetStudentRecordById(pollAnswer.user.id)
        dayRecord.lessons = [
            StudentStatusAtLesson.Attended if not i in pollAnswer.option_ids else StudentStatusAtLesson.Missed
            for i in range(len(dayRecord.lessons))]

    def SendStatisticToSupervisor(self):
        if not self.checkOnCompulsoryParams(): return
        print('Attempt to send statistic to Supervisor')
        if self._groupInfo.SupervisorId == 0: return
        self._bot.send_message(self._groupInfo.SupervisorId, self.GenerateDayStatisticReport())

    def SendStatisticToAdmin(self):
        if not self.checkOnCompulsoryParams(): return
        print('Attempt to send statistic to Admin')
        if self._groupInfo.SupervisorId == 0: return
        self._bot.send_message(self._groupInfo.AdminId, self.GenerateDayStatisticReport())

    def ProcessPrivateMessage(self, message: t.Message):
        if 'стат' in message.text.lower() and \
                (message.from_user.id == self._groupInfo.SupervisorId or
                 message.from_user.id == self._groupInfo.AdminId):
            print('Pre-time sending stat')
            if message.from_user.id == self._groupInfo.AdminId:
                self.SendStatisticToAdmin()
            else:
                self.SendStatisticToSupervisor()
        if 'закрыть' in message.text.lower() and \
                (message.from_user.id == self._groupInfo.SupervisorId or
                 message.from_user.id == self._groupInfo.AdminId):
            print('Pre-time reopening by', message.from_user.username)
            self.CloseDayAndDeletePoll()
            self.OpenDayAndSendNewPoll()
            global isDayReopened
            isDayReopened = True


# --------------------------Main------------------------------------ #


def threadFunc():
    global isDayReopened
    while True:
        if not dayStatCollector.checkOnCompulsoryParams() and not dayStatCollector.isPollingGranted:
            continue
        nowHour = datetime.datetime.now().hour.real
        if nowHour == 19 and not isDayReopened:
            print('Procedure of closing day started')
            dayStatCollector.CloseDayAndDeletePoll()
            print('Procedure of closing day compete')
            print('Procedure of opening new day started')
            dayStatCollector.OpenDayAndSendNewPoll()
            print('Procedure of opening day complete')
            isDayReopened = True
        if nowHour == 20 and isDayReopened:
            isDayReopened = False
        time.sleep(10)


token = ''
loadPresetSettings()
bot = telebot.TeleBot(token)
dayStatCollector = DayStatisticCollector(bot, groupInfo)
print('Current week:', getWeekNumber())
if groupInfo.ChatId == 0:
    registerChatPassphrase = ''
    for ch in [chr(ord('a') + random.randint(0, 25)) for i in range(10)]:
        registerChatPassphrase += ch
    print('Passphrase to register chat:', registerChatPassphrase)
else:
    print('Preset Chat loaded')
    dayStatCollector.CollectDataAboutStudents()

isDayReopened = False

thread = Thread(target=threadFunc)
thread.start()


# ------------------Handlers--------------------- #

@bot.message_handler(chat_types=['supergroup', 'group', 'gigagroup'])
def processMessageGroupChat(message: t.Message):
    if groupInfo.ChatId == 0 and message.text == registerChatPassphrase:
        bot.send_message(message.chat.id, 'Чат зарегистрирован')
        groupInfo.ChatId = message.chat.id
        bot.delete_message(message.chat.id, message.id)
        dayStatCollector.CollectDataAboutStudents()
        savePresetData()


@bot.message_handler(chat_types=['private'])
def processMessagePrivateChat(message: t.Message):
    dayStatCollector.CheckOnAdminOrSupervisorRegister(message)
    dayStatCollector.ProcessPrivateMessage(message)
    savePresetData()


def filter(pollAnswer):
    return True


@bot.poll_answer_handler(filter)
def processPollAnswer(pollAnswer: t.PollAnswer):
    dayStatCollector.ProcessPollAnswer(pollAnswer)


bot.infinity_polling()
