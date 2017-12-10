import tensorflow as tf
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

OPTIMIZER_DICT = {'sgd': tf.train.GradientDescentOptimizer,  # Gradient Descent
                  'adadelta': tf.train.AdadeltaOptimizer,  # Adadelta
                  'adagrad': tf.train.AdagradOptimizer,  # Adagrad
                  'adam': tf.train.AdamOptimizer,  # Adam
                  'rmsprop': tf.train.RMSPropOptimizer  # RMSprop
                  }

FLAGS = None


def load_mnist_images(binarize=True):
    """
    :param binarize: Turn the images into binary vectors
    :return: x_train, x_test  Where
        x_train is a (55000 x 784) tensor of training images
        x_test is a  (10000 x 784) tensor of test images
    """
    from tensorflow.examples.tutorials.mnist import input_data
    mnist = input_data.read_data_sets("/tmp/data/", one_hot=False)
    x_train = mnist.train.images
    x_test = mnist.test.images
    if binarize:
        x_train = (x_train > 0.5).astype(x_train.dtype)
        x_test = (x_test > 0.5).astype(x_test.dtype)
    return x_train, x_test


class NaiveBayesModel(object):

    def __init__(self, w_init, b_init=None, c_init=None):
        """
        :param w_init: An (n_categories, n_dim) array, where w[i, j] represents log p(X[j]=1 | Z[i]=1)
        :param b_init: A (n_categories, ) vector where b[i] represents log p(Z[i]=1), or None to fill with zeros
        :param c_init: A (n_dim, ) vector where b[j] represents log p(X[j]=1), or None to fill with zeros
        """
        self.w_init = w_init
        self.b_init = b_init
        self.c_init = c_init

        init = tf.constant_initializer(0.0)

        self.w = tf.get_variable(name="w", shape=self.w_init, dtype=tf.float32)
        self.b = tf.get_variable(
            name="b", shape=self.b_init, dtype=tf.float32, initializer=init)
        self.c = tf.get_variable(
            name="c", shape=self.c_init, dtype=tf.float32, initializer=init)

        self.n_categories = w_init[0]
        self.n_dims = w_init[1]
        self.n_labels = w_init[0]

    def log_p_x_given_z(self, x, z=None):
        """
        :param x: An (n_samples, n_dims) tensor
        :param z: An (n_samples, n_labels) tensor of integer class labels
        :return: An (n_samples, n_labels) tensor  p_x_given_z where result[i, j] indicates p(X=x[i] | Z=z[j])
        """
        batch_size = tf.shape(x)[0]

        # reshape x into [batch_size, n_labels, n_dims]
        X = tf.tile(x, [1, self.n_labels])
        X = tf.reshape(X, [batch_size, self.n_labels, self.n_dims])

        dist = tf.distributions.Bernoulli(probs=tf.sigmoid(self.w + self.c))
        log_p_x_given_z = tf.reduce_sum(dist.log_prob(X), axis=2)

        return log_p_x_given_z

    def log_p_x(self, x):
        """
        :param x: A (n_samples, n_dim) array of data points
        :return: A (n_samples, ) array of log-probabilities assigned to each point
        """
        log_pxz = self.log_p_x_given_z(x)
        log_px = tf.reduce_logsumexp(
            tf.nn.log_softmax(self.b) + log_pxz, axis=-1)

        return log_px

    def sample(self, n_samples):
        """
        :param n_samples: Generate N samples from your model
        :return: A (n_samples, n_dim) array where n_dim is the dimensionality of your input
        """
        prob = tf.sigmoid(self.w + self.c)
        samples = np.zeros((n_samples, self.n_dims))
        sampled_latent_variables = list()

        for n in range(n_samples):

            # Sample a random latent state
            z = np.random.choice(self.n_labels, 1)[0]
            sampled_latent_variables.append(z)

            # Extract Bernoulli Pixel distribution for sampled latent variable.
            dist = tf.distributions.Bernoulli(probs=prob[z])
            samples[n] = dist.sample(1).eval()

        return samples, sampled_latent_variables

    def plot_samples(self, samples, sampled_latent_variables, i):

        plt.figure()
        for idx in range(samples.shape[0]):
            plt.subplot(4, 4, idx + 1)
            plt.text(
                0, 1, sampled_latent_variables[idx], color='black', backgroundcolor='white', fontsize=8)
            plt.imshow(samples[idx].reshape(28, 28), cmap='gray')
            plt.axis('off')
        plt.savefig('./NB_%s.png' % str(i))
        plt.close()

    def train_step(self, loss, flags):

        optimizer = flags[0]
        learning_rate = flags[1]

        train_step = optimizer(learning_rate).minimize(loss)

        return train_step


def train_simple_generative_model_on_mnist(n_categories=20, initial_mag=0.01, optimizer='rmsprop', learning_rate=.01, n_epochs=20, test_every=100,
                                           minibatch_size=100, plot_n_samples=16):
    """
    Train a simple Generative model on MNIST and plot the results.

    :param n_categories: Number of latent categories (K in assignment)
    :param initial_mag: Initial weight magnitude
    :param optimizer: The name of the optimizer to use
    :param learning_rate: Learning rate for the optimization
    :param n_epochs: Number of epochs to train for
    :param test_every: Test every X iterations
    :param minibatch_size: Number of samples in a minibatch
    :param plot_n_samples: Number of samples to plot
    """

    # Get Data
    x_train, x_test = load_mnist_images(binarize=True)
    train_iterator = tf.data.Dataset.from_tensor_slices(
        x_train).repeat().batch(minibatch_size).make_initializable_iterator()
    n_samples, n_dims = x_train.shape
    x_minibatch = train_iterator.get_next()  # Get symbolic data, target tensors

    # Build the model
    nb = NaiveBayesModel(w_init=(n_categories, n_dims),
                         b_init=n_categories, c_init=n_dims)

    # Build Graph
    train_log_px = nb.log_p_x(x_minibatch)
    train_loss = -1 * tf.reduce_mean(train_log_px)

    test_log_px = nb.log_p_x(x_test)
    test_loss = -1 * tf.reduce_mean(test_log_px)

    train_step = nb.train_step(train_loss, flags=(
        OPTIMIZER_DICT["rmsprop"], learning_rate))

    with tf.Session() as sess:

        sess.run(train_iterator.initializer)
        sess.run(tf.global_variables_initializer())
        n_steps = (n_epochs * n_samples) / minibatch_size
        loss_list = list()

        for i in range(int(n_steps)):

            _, tr_loss = sess.run([train_step, train_loss])

            if i % test_every == 0:

                # Determine Test Loss
                te_loss = sess.run([test_loss])
                print("[{}] Train Step {:04d}/{:04d}, Batch Size = {}, Training Loss = {} , Test Loss = {}"
                      .format(datetime.now().strftime("%Y-%m-%d %H:%M"), i + 1,
                              int(n_steps), minibatch_size, tr_loss, te_loss))

                # Sample outputs
                samples, sampled_latent_variables = nb.sample(plot_n_samples)
                nb.plot_samples(samples, sampled_latent_variables, i)


if __name__ == '__main__':
    train_simple_generative_model_on_mnist()
