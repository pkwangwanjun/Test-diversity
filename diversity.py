#!/usr/bin/env python2
# -*- coding: utf-8 -*-
import keras
from keras import Model,Input
from keras.models import load_model
from keras.layers import Activation,Flatten
import math
import numpy as np
import pandas as pd
import foolbox
import cv2
from tqdm import tqdm
#导入数据集
from keras.datasets import mnist

from sklearn.metrics import accuracy_score
from sklearn.metrics import roc_auc_score

import scipy
import sys, os
import networkx as nx
from scipy.linalg.misc import norm
import multiprocessing


def adv_example(x,y,model_path='./model/model_mnist.hdf5'):
    keras.backend.set_learning_phase(0)
    model=load_model(model_path)
    foolmodel=foolbox.models.KerasModel(model,bounds=(0,1),preprocessing=(0,1))
    attack=foolbox.attacks.IterativeGradientAttack(foolmodel)
    #attack=foolbox.attacks.DeepFoolL2Attack(foolmodel)
    result=[]
    for image in tqdm(x):
        #adv=attack(image.reshape(28,28,-1),label=y,steps=1000,subsample=10)
        adv=attack(image.reshape(28,28,-1),y,epsilons=[0.01,0.1],steps=10)
        if isinstance(adv,np.ndarray):
            result.append(adv)
        else:
            print('adv fail')
    return np.array(result)


def get_thin(image):
    kernel = np.ones((2,2),np.uint8)
    erosion = cv2.erode(image,kernel,iterations=1)
    return erosion.reshape(28,28,1)

def get_fat(image):
    kernel = np.ones((2,2),np.uint8)
    dilation = cv2.dilate(image,kernel,iterations=1)
    return dilation.reshape(28,28,1)


def generate_mnist_sample(label,ratio=0.1):
    (X_train, Y_train), (X_test, Y_test) = mnist.load_data()  # 28*28
    X_train = X_train.astype('float32').reshape(-1,28,28,1)
    X_test = X_test.astype('float32').reshape(-1,28,28,1)
    X_train /= 255
    X_test /= 255

    image_org=X_test[Y_test==label]

    choice_index=np.random.choice(range(len(image_org)),size=int(len(image_org)*ratio),replace=False)
    image_org=image_org[choice_index]

    fat=[]
    thin=[]
    for img in image_org:
        fat.append(get_fat(img))
        thin.append(get_thin(img))
    fat=np.array(fat)
    thin=np.array(thin)
    adv=adv_example(image_org,label)
    return image_org,fat,thin,adv

def graph_distance(x,span=True):
    '''
    x是采样的图片向量
    x是ndarray
    '''
    if not isinstance(x,np.ndarray):
        return False
    x=np.concatenate([x,np.eye(x.shape[1])])
    num=len(x)
    G=nx.complete_graph(num)
    arr=np.ones((num,num))
    weight_edge=[]
    for i in range(num):
        for j in range(num):
            temp=norm(x[i]-x[j])
            arr[i][j]=temp
            weight_edge.append((i,j,temp))
            #weight_edge=[(i,j,norm(x[i]-x[j])) for i in range(num) for j in range(num)]
    G.add_weighted_edges_from(weight_edge)
    if span:
        span_tree=nx.minimum_spanning_tree(G)
        span_edge=span_tree.edges()
        #epsilons=10e-30
    else:
        choice_index=np.random.choice(range(len(G.edges())),size=num-1,replace=False)
        span_edge=np.array(G.edges())[choice_index]
    w_sum=0
    p=[]
    for index in span_edge:
        p.append(arr[tuple(index)])
        w_sum+=arr[tuple(index)]
    p=np.array(p)/w_sum
    result=-p*np.log(p)
    result[np.isnan(result)]=0
    return result.sum()


def Exp_one(image,label,size=500,sample_epoch=500):
    model=load_model('model/model_mnist.hdf5')
    pred=model.predict(image)
    acc=[]
    entropy=[]
    random_entropy=[]
    auc_macro=[]
    auc_micro=[]
    label_onehot=pd.get_dummies(label).values
    for i in tqdm(range(sample_epoch)):
        index_choice=np.random.choice(range(image.shape[0]),size=size,replace=False)
        acc.append(accuracy_score(label[index_choice],np.argmax(pred[index_choice],axis=1)))
        entropy.append(graph_distance(pred[index_choice]))
        random_entropy.append(graph_distance(pred[index_choice],span=False))

        #auc_macro.append(roc_auc_score(label_onehot[index_choice],pred[index_choice],average='macro'))
        auc_micro.append(roc_auc_score(label_onehot[index_choice],pred[index_choice],average='micro'))
    return acc,entropy,random_entropy,auc_micro


def pool_func(size,sample_epoch):
    image=[]
    label=[]
    for i in range(10):
        org,fat,thin,adv=generate_mnist_sample(label=i,ratio=0.1)
        temp_image=np.concatenate([org,fat,thin,adv],axis=0)
        temp_label=i*np.ones(len(temp_image))
        image.append(temp_image.copy())
        label.append(temp_label.copy())
    image=np.concatenate(image,axis=0)
    label=np.concatenate(label,axis=0)
    acc,entropy,random_entropy,auc_micro=Exp_one(image,label,size=size,sample_epoch=sample_epoch)
    df=pd.DataFrame([acc,entropy,random_entropy,auc_micro])
    df.to_csv('./exp_output/mnist_{}.csv'.format(size))



if __name__=='__main__':
    pool = multiprocessing.Pool(processes=2)
    sample_epoch=500
    for size in [20,50]:
        pool.apply_async(pool_func, (size,sample_epoch,))
    pool.close()
    pool.join()