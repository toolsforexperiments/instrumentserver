import json


def projectCard(filename):
	with open(filename) as j:
		dict_ = json.load(j)
	print(dict_)
	for keys in dict_:
		print(dict_[keys][0]['Sweeping varaibles'])




	return


if __name__ == '__main__':
	projectCard('projectCard.json')